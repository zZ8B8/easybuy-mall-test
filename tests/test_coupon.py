# -*- coding: utf-8 -*-
"""优惠券模块 · 接口测试

覆盖：
    · 领券中心（列表、券型、剩余量）
    · 领取（正常 / 异常 / 未登录 / 计数递增）
    · 我的券包（列表、过期状态、状态过滤、用户隔离）
    · 下单抵扣（三种券型、门槛边界、过期券、越权用券）
    · 金额对账（实付 == 小计 - 优惠）
    · 券状态流转（核销、取消退券）

初始数据（seed.sql）：
    user_a → 券#1 无门槛减10、券#2 满100减20、券#3 全场88折
    user_b → 券#4 满100减20
    demo   → 券#5 满50打95折、券#6 已过期
"""
import pytest

from tests.client import ApiClient
from tests.conftest import BASE_URL, stock_of


def order_with_coupon(client, product_id, quantity=1, user_coupon_id=None):
    """加购 -> 下单（可选带券），返回 (status, body)。"""
    client.add_to_cart(product_id, quantity)
    cart_ids = [client.cart_items()[0]["id"]]
    payload = {"cartIds": cart_ids}
    if user_coupon_id:
        payload["userCouponId"] = user_coupon_id
    return client.post("/api/orders", payload)


@pytest.fixture
def demo(api):
    """已登录的 demo 账号（持有过期券）。"""
    c = ApiClient(BASE_URL)
    c.login("demo")
    return c


# ======================================================================
# 领券中心
# ======================================================================
class TestCouponCenter:

    def test_list_active_coupons(self, api):
        """正常：领券中心返回 5 张有效券，过期的那张不出现"""
        status, body = api.get("/api/coupons")
        assert status == 200
        ids = [c["id"] for c in body["data"]["items"]]
        assert len(ids) == 5
        assert 6 not in ids, "已过期的券#6 不应出现在领券中心"

    def test_three_coupon_types(self, api):
        """正常：三种券型都能领到"""
        _, body = api.get("/api/coupons")
        types = {c["type"] for c in body["data"]["items"]}
        assert types == {"THRESHOLD", "DISCOUNT", "FREE"}

    def test_coupon_fields(self, api):
        """正常：券的关键字段完整"""
        _, body = api.get("/api/coupons")
        c = [x for x in body["data"]["items"] if x["id"] == 2][0]
        assert c["code"] == "FULL100"
        assert c["type"] == "THRESHOLD"
        assert c["threshold"] == 100.0
        assert c["value"] == 20.0
        assert c["per_user_limit"] == 1

    def test_remain_count(self, api):
        """正常：剩余量 = 总量 - 已领（不限量用 -1 表示）"""
        _, body = api.get("/api/coupons")
        by_id = {c["id"]: c for c in body["data"]["items"]}
        assert by_id[2]["remain"] == 498      # 500 - 2
        assert by_id[3]["remain"] == 300      # 300 - 0
        assert by_id[4]["remain"] == 199      # 200 - 1

    def test_no_login_required(self, api):
        """正常：领券中心不需要登录就能看"""
        assert api.get("/api/coupons")[0] == 200


# ======================================================================
# 领取
# ======================================================================
class TestClaimCoupon:

    def test_claim_success(self, user_a):
        """正常：领取一张还没领过的券"""
        status, body = user_a.post("/api/coupons/3/claim", {})
        assert status == 200
        assert body["data"]["couponId"] == 3
        assert body["data"]["status"] == "UNUSED"

    def test_claim_then_in_my_pack(self, user_a):
        """正常：领完立刻出现在券包里"""
        user_a.post("/api/coupons/3/claim", {})
        _, body = user_a.get("/api/user/coupons")
        assert 3 in [c["coupon_id"] for c in body["data"]["items"]]

    def test_claim_increases_count(self, user_a, db):
        """数据一致性：领券后 claimed_count +1"""
        with db.cursor() as cur:
            cur.execute("SELECT claimed_count FROM coupons WHERE id=3")
            before = cur.fetchone()[0]
        user_a.post("/api/coupons/3/claim", {})
        with db.cursor() as cur:
            cur.execute("SELECT claimed_count FROM coupons WHERE id=3")
            after = cur.fetchone()[0]
        assert after == before + 1

    def test_claim_not_exist(self, user_a):
        """异常场景：领不存在的券 -> 404"""
        status, body = user_a.post("/api/coupons/99999/claim", {})
        assert status == 404
        assert body["code"] == "COUPON_NOT_FOUND"

    def test_claim_expired_coupon(self, user_a):
        """异常场景：领已过期的券 -> 404（领券中心也不展示）"""
        status, body = user_a.post("/api/coupons/6/claim", {})
        assert status == 404

    def test_claim_requires_login(self, api):
        """异常场景：未登录不能领券"""
        status, body = api.post("/api/coupons/3/claim", {})
        assert status == 401


# ======================================================================
# 我的券包
# ======================================================================
class TestMyCoupons:

    def test_my_coupons_initial(self, user_a):
        """正常：user_a 初始持有 3 张券"""
        status, body = user_a.get("/api/user/coupons")
        assert status == 200
        assert len(body["data"]["items"]) == 3

    def test_expired_coupon_marked(self, demo):
        """正常：过期券状态为 EXPIRED 且 usable=false"""
        _, body = demo.get("/api/user/coupons")
        row = [c for c in body["data"]["items"] if c["id"] == 6][0]
        assert row["status"] == "EXPIRED"
        assert row["usable"] is False

    def test_filter_unused(self, user_a):
        """正常：按状态过滤 —— 未使用的 3 张"""
        _, body = user_a.get("/api/user/coupons?status=UNUSED")
        assert len(body["data"]["items"]) == 3

    def test_filter_used_empty(self, user_a):
        """边界-空：还没用券，USED 列表为空"""
        _, body = user_a.get("/api/user/coupons?status=USED")
        assert body["data"]["items"] == []

    def test_requires_login(self, api):
        """异常场景：未登录不能看券包"""
        assert api.get("/api/user/coupons")[0] == 401

    def test_isolated_between_users(self, user_a, user_b):
        """用户隔离：A 的券不会出现在 B 的券包里"""
        _, a = user_a.get("/api/user/coupons")
        _, b = user_b.get("/api/user/coupons")
        ids_a = {c["id"] for c in a["data"]["items"]}
        ids_b = {c["id"] for c in b["data"]["items"]}
        assert ids_a.isdisjoint(ids_b)


# ======================================================================
# 下单抵扣
# ======================================================================
class TestOrderWithCoupon:

    def test_no_coupon(self, user_a):
        """正常：不用券，优惠为 0，实付 == 小计"""
        status, body = order_with_coupon(user_a, 1, 1)
        assert status == 200
        o = body["data"]
        assert o["discount_amount"] == 0
        assert o["amount"] == pytest.approx(o["total_amount"])

    def test_threshold_coupon(self, user_a):
        """正常：满100减20，买 199 的耳机 -> 实付 179"""
        status, body = order_with_coupon(user_a, 1, 1, user_coupon_id=2)
        assert status == 200
        o = body["data"]
        assert o["total_amount"] == pytest.approx(199.0)
        assert o["discount_amount"] == pytest.approx(20.0)
        assert o["amount"] == pytest.approx(179.0)

    def test_free_coupon_on_cheap_item(self, user_a):
        """正常：无门槛券买 59.90 的 T 恤也能用 -> 实付 49.90"""
        status, body = order_with_coupon(user_a, 4, 1, user_coupon_id=1)
        assert status == 200
        o = body["data"]
        assert o["discount_amount"] == pytest.approx(10.0)
        assert o["amount"] == pytest.approx(49.90)

    def test_amount_identity(self, user_a):
        """数据一致性：实付 == 小计 - 优惠"""
        _, body = order_with_coupon(user_a, 1, 2, user_coupon_id=2)
        o = body["data"]
        assert o["amount"] == pytest.approx(o["total_amount"] - o["discount_amount"])

    def test_coupon_name_in_order(self, user_a):
        """正常：订单详情带上券名，方便前端展示"""
        _, body = order_with_coupon(user_a, 1, 1, user_coupon_id=2)
        assert body["data"]["coupon_name"] == "满 100 减 20"

    def test_threshold_not_met(self, user_a, db):
        """边界值：小计 59.90 用「满100减20」-> 400，且库存不动"""
        before = stock_of(db, 4)
        status, body = order_with_coupon(user_a, 4, 1, user_coupon_id=2)
        assert status == 400
        assert body["code"] == "COUPON_THRESHOLD_NOT_MET"
        assert stock_of(db, 4) == before, "券不能用时绝不能扣库存"

    def test_threshold_exactly_met(self, user_a):
        """边界值：小计刚好 129 > 门槛 100 -> 可以用"""
        status, body = order_with_coupon(user_a, 3, 1, user_coupon_id=2)
        assert status == 200
        assert body["data"]["amount"] == pytest.approx(129.0 - 20.0)

    def test_expired_coupon_rejected(self, demo):
        """异常场景：过期券不能用 -> 400"""
        status, body = order_with_coupon(demo, 1, 1, user_coupon_id=6)
        assert status == 400
        assert body["code"] == "COUPON_EXPIRED"

    def test_cannot_use_others_coupon(self, user_b):
        """越权防护：拿别人的券下单 -> 404（不暴露「这张券是别人的」）"""
        status, body = order_with_coupon(user_b, 1, 1, user_coupon_id=1)
        assert status == 404
        assert body["code"] == "COUPON_NOT_FOUND"

    def test_coupon_not_exist(self, user_a):
        """异常场景：券不存在 -> 404"""
        status, body = order_with_coupon(user_a, 1, 1, user_coupon_id=99999)
        assert status == 404
        assert body["code"] == "COUPON_NOT_FOUND"

    def test_requires_login(self, api):
        """异常场景：未登录不能下单"""
        assert api.post("/api/orders", {"cartIds": [1], "userCouponId": 2})[0] == 401


# ======================================================================
# 券状态流转
# ======================================================================
class TestCouponLifecycle:

    def test_coupon_marked_used(self, user_a, db):
        """数据一致性：下单后券被核销，并记录使用的订单号"""
        _, body = order_with_coupon(user_a, 1, 1, user_coupon_id=2)
        oid = body["data"]["id"]
        with db.cursor() as cur:
            cur.execute("SELECT status, order_id FROM user_coupons WHERE id=2")
            row = cur.fetchone()
        assert row[0] == "USED"
        assert row[1] == oid

    def test_cancel_returns_coupon(self, user_a, db):
        """正常：取消订单要把券退回给用户"""
        _, body = order_with_coupon(user_a, 1, 1, user_coupon_id=2)
        oid = body["data"]["id"]
        status, _ = user_a.cancel(oid)
        assert status == 200
        with db.cursor() as cur:
            cur.execute("SELECT status, order_id FROM user_coupons WHERE id=2")
            row = cur.fetchone()
        assert row[0] == "UNUSED", "取消订单后券应回到未使用"
        assert row[1] is None

    def test_used_coupon_shows_in_used_list(self, user_a):
        """正常：用掉的券会出现在 USED 列表里"""
        order_with_coupon(user_a, 1, 1, user_coupon_id=2)
        _, body = user_a.get("/api/user/coupons?status=USED")
        assert [c["id"] for c in body["data"]["items"]] == [2]
