# -*- coding: utf-8 -*-
"""订单模块 · 接口测试

这是整个商城最核心的模块，覆盖：
    · 下单主流程与状态迁移
    · 库存扣减的正确性（含「用库存流水反向对账」）
    · 金额计算精度
    · 订单归属隔离
"""
import pytest

from tests.conftest import stock_of


def make_order(client, product_id, quantity=1):
    """辅助：加购 -> 下单，返回订单数据"""
    client.add_to_cart(product_id, quantity)
    cid = client.cart_items()[0]["id"]
    status, body = client.create_order([cid])
    assert status == 200, "下单失败：%s" % body
    return body["data"]


# ======================================================================
# 下单
# ======================================================================
class TestCreateOrder:

    def test_create_order_success(self, user_a):
        """正常：下单成功，初始状态为 PENDING"""
        order = make_order(user_a, 1, 2)
        assert order["status"] == "PENDING"
        assert order["amount"] == pytest.approx(199.0 * 2)
        assert order["paid_at"] is None

    def test_order_items_snapshot(self, user_a):
        """正常：订单明细保存了下单当时的商品名与单价（快照）"""
        order = make_order(user_a, 2, 1)
        item = order["items"][0]
        assert item["product_name"] == "机械键盘 87键"
        assert item["price"] == 329.5
        assert item["quantity"] == 1

    def test_cart_cleared_after_order(self, user_a):
        """正常：下单后对应的购物车行被清掉"""
        user_a.add_to_cart(1, 1)
        cid = user_a.cart_items()[0]["id"]
        user_a.create_order([cid])
        assert user_a.cart_items() == []

    def test_empty_cart_ids(self, user_a):
        """边界-空：cartIds 为空数组"""
        status, body = user_a.create_order([])
        assert status == 400
        assert body["code"] == "EMPTY_CART"

    def test_cart_id_not_exist(self, user_a):
        """异常场景：购物车行不存在 -> 404（资源不存在）"""
        status, body = user_a.create_order([99999])
        assert status == 404
        assert body["code"] == "CART_NOT_FOUND"

    def test_cannot_order_others_cart(self, user_a, user_b):
        """越权防护：不能拿别人的购物车行下单 -> 404（对外不暴露「这行存在」）"""
        user_a.add_to_cart(1, 1)
        cid = user_a.cart_items()[0]["id"]
        status, body = user_b.create_order([cid])
        assert status == 404
        assert body["code"] == "CART_NOT_FOUND"
        assert len(user_a.cart_items()) == 1, "A 的购物车不应被消耗"

    def test_requires_login(self, api):
        """异常场景：未登录不能下单"""
        status, body = api.create_order([1])
        assert status == 401

    # ------------------------------------------------------------------
    # 库存相关（等价类 + 边界值）
    # ------------------------------------------------------------------
    @pytest.mark.parametrize("qty", [1, 3])
    def test_stock_boundary_ok(self, user_a, db, qty):
        """边界值：商品 3 库存为 3，买 1 件和买 3 件都应成功"""
        order = make_order(user_a, 3, qty)
        assert order["status"] == "PENDING"
        assert stock_of(db, 3) == 3 - qty

    def test_stock_boundary_exceeded(self, user_a, db):
        """边界值：库存 3，买 4 件 -> 库存不足"""
        user_a.add_to_cart(3, 4)
        cid = user_a.cart_items()[0]["id"]
        status, body = user_a.create_order([cid])
        assert status == 400
        assert body["code"] == "INSUFFICIENT_STOCK"
        assert "仅剩 3 件" in body["message"]
        assert stock_of(db, 3) == 3, "下单失败时库存不应变动"

    def test_stock_boundary_exact(self, user_a, db):
        """边界值：库存 3，买 3 件 -> 成功且库存归零"""
        make_order(user_a, 3, 3)
        assert stock_of(db, 3) == 0

    def test_quantity_over_limit(self, user_a):
        """边界值：单笔数量上限 99，买 100 件被拒"""
        user_a.add_to_cart(4, 100)       # 商品 4 库存 100，但单笔上限 99
        cid = user_a.cart_items()[0]["id"]
        status, body = user_a.create_order([cid])
        assert status == 400
        assert body["code"] == "INVALID_PARAM"

    def test_multi_product_order(self, user_a, db):
        """正常：一次下单多个商品"""
        user_a.add_to_cart(1, 1)
        user_a.add_to_cart(4, 2)
        ids = [i["id"] for i in user_a.cart_items()]
        status, body = user_a.create_order(ids)
        assert status == 200
        assert body["data"]["amount"] == pytest.approx(199.0 + 59.9 * 2)
        assert len(body["data"]["items"]) == 2
        assert stock_of(db, 1) == 49
        assert stock_of(db, 4) == 98


# ======================================================================
# 库存一致性：用 stock_logs 反向对账
# ======================================================================
class TestStockConsistency:

    def test_stock_matches_logs_after_order(self, user_a, db):
        """数据一致性：下单后「商品库存」应等于「库存流水合计」"""
        make_order(user_a, 1, 3)
        with db.cursor() as cur:
            cur.execute("SELECT stock FROM products WHERE id=1")
            stock = cur.fetchone()[0]
            cur.execute("SELECT COALESCE(SUM(change_qty),0) FROM stock_logs WHERE product_id=1")
            logs = cur.fetchone()[0]
        assert stock == logs, "库存与流水不一致：stock=%s, logs=%s" % (stock, logs)

    def test_stock_matches_logs_after_cancel(self, user_a, db):
        """数据一致性：取消订单回滚库存后，账仍然对得上"""
        order = make_order(user_a, 1, 3)
        user_a.cancel(order["id"])
        with db.cursor() as cur:
            cur.execute("SELECT stock FROM products WHERE id=1")
            stock = cur.fetchone()[0]
            cur.execute("SELECT COALESCE(SUM(change_qty),0) FROM stock_logs WHERE product_id=1")
            logs = cur.fetchone()[0]
        assert stock == logs
        assert stock == 50, "取消后库存应回到初始值"

    def test_stock_log_reason_recorded(self, user_a, db):
        """数据一致性：流水要记录变动原因和关联订单"""
        order = make_order(user_a, 1, 2)
        with db.cursor() as cur:
            cur.execute(
                "SELECT change_qty, reason, order_id FROM stock_logs "
                "WHERE product_id=1 AND reason='ORDER_CREATE'"
            )
            row = cur.fetchone()
        assert row[0] == -2
        assert row[2] == order["id"]


# ======================================================================
# 查询
# ======================================================================
class TestOrderQuery:

    def test_order_list_empty(self, user_a):
        """边界-空：新用户没有订单"""
        status, body = user_a.get("/api/orders")
        assert status == 200
        assert body["data"]["items"] == []

    def test_order_list_isolated(self, user_a, user_b):
        """用户隔离：只能看到自己的订单"""
        make_order(user_a, 1, 1)
        assert len(user_a.get("/api/orders")[1]["data"]["items"]) == 1
        assert user_b.get("/api/orders")[1]["data"]["items"] == []

    def test_order_detail(self, user_a):
        """正常：查订单详情带明细"""
        order = make_order(user_a, 5, 1)
        status, body = user_a.order(order["id"])
        assert status == 200
        assert body["data"]["id"] == order["id"]
        assert len(body["data"]["items"]) == 1

    def test_order_detail_not_found(self, user_a):
        """异常场景：订单不存在 -> 404"""
        status, body = user_a.order(99999)
        assert status == 404
        assert body["code"] == "ORDER_NOT_FOUND"


# ======================================================================
# 支付
# ======================================================================
class TestPayOrder:

    def test_pay_success(self, user_a, db):
        """正常：支付成功，状态变 PAID 且记录支付时间与方式"""
        order = make_order(user_a, 1, 1)
        status, body = user_a.pay(order["id"], "ALIPAY")
        assert status == 200
        assert body["data"]["status"] == "PAID"
        assert body["data"]["pay_type"] == "ALIPAY"
        assert body["data"]["paid_at"] is not None

        with db.cursor() as cur:
            cur.execute("SELECT status, pay_type FROM orders WHERE id=%s", (order["id"],))
            assert cur.fetchone() == ("PAID", "ALIPAY")

    def test_pay_wechat(self, user_a):
        """等价类：支付方式 WECHAT"""
        order = make_order(user_a, 1, 1)
        _, body = user_a.pay(order["id"], "WECHAT")
        assert body["data"]["pay_type"] == "WECHAT"

    def test_pay_not_found(self, user_a):
        """异常场景：支付不存在的订单 -> 404"""
        status, body = user_a.pay(99999)
        assert status == 404

    def test_pay_twice(self, user_a):
        """幂等性：重复支付同一订单应被拒绝

        修复 BUG-001 时一并覆盖：pay_order 现在只放行 PENDING 状态，
        第二次支付返回 400 INVALID_STATUS。
        """
        order = make_order(user_a, 1, 1)
        assert user_a.pay(order["id"])[0] == 200
        status, body = user_a.pay(order["id"])
        assert status == 400, "重复支付应被拒绝"
        assert body["code"] == "INVALID_STATUS"


# ======================================================================
# 取消
# ======================================================================
class TestCancelOrder:

    def test_cancel_rollback_stock(self, user_a, db):
        """正常：取消订单，库存回滚"""
        order = make_order(user_a, 1, 3)
        assert stock_of(db, 1) == 47
        status, body = user_a.cancel(order["id"])
        assert status == 200
        assert body["data"]["status"] == "CANCELLED"
        assert stock_of(db, 1) == 50

    def test_cancel_not_found(self, user_a):
        """异常场景：取消不存在的订单 -> 404"""
        status, body = user_a.cancel(99999)
        assert status == 404

    @pytest.mark.xfail(reason="BUG-001：已支付订单仍可被取消（缺状态校验）", strict=True)
    def test_cancel_paid_order_should_fail(self, user_a):
        """业务规则：已支付的订单不应被允许取消

        当前实现没有拦截 —— 与 BUG-001 同源，详见 docs/缺陷报告.md。
        """
        order = make_order(user_a, 1, 1)
        user_a.pay(order["id"])
        status, body = user_a.cancel(order["id"])
        assert status == 400, "已支付订单应当不允许取消"
