# -*- coding: utf-8 -*-
"""BUG-006 · 优惠券可以重复使用

缺陷类型：状态机 / 业务规则缺失
严重级别：高
根因：_load_user_coupon() 校验了「券存在」「归属正确」「未过期」，
      **唯独没校验「是否已被使用」**。

      下单成功后，券确实被标记成了 USED（界面上显示「已使用」），
      但下单接口根本不读这个状态，于是同一张券可以反复抵扣。
      这就是典型的「接口行为与界面展示不一致」——
      只点页面看不出问题，一写接口脚本立刻现形。

影响：
    · 一张「满 100 减 20」的券可以被无限次使用，平台持续让利
    · 对账时 discount_amount 总和远大于券的发放总额，账目对不上

复现：见下方用例 —— 连下两单用同一张券，第二单仍然抵扣成功。

修复思路：_load_user_coupon 里加上
        if uc["status"] == "USED": raise ApiError("COUPON_USED", ...)
"""
import pytest


def order_with_coupon(client, product_id, quantity=1, user_coupon_id=None):
    client.add_to_cart(product_id, quantity)
    cart_ids = [client.cart_items()[0]["id"]]
    payload = {"cartIds": cart_ids}
    if user_coupon_id:
        payload["userCouponId"] = user_coupon_id
    return client.post("/api/orders", payload)


@pytest.mark.xfail(reason="BUG-006：已使用的优惠券未被拦截，可重复抵扣", strict=True)
def test_used_coupon_cannot_be_reused(user_a):
    """业务规则：一张券只能抵扣一次

    第一单用券#2（满100减20）成功；
    第二单继续用同一张券#2 —— 应当返回 400，实际仍然抵扣成功。
    """
    first_status, _ = order_with_coupon(user_a, 1, 1, user_coupon_id=2)
    assert first_status == 200, "第一单应正常下单"

    second_status, second_body = order_with_coupon(user_a, 1, 1, user_coupon_id=2)
    assert second_status == 400, (
        "已使用的券不应再次抵扣，实际返回 %s，抵扣了 %s 元"
        % (second_status, (second_body.get("data") or {}).get("discount_amount"))
    )


@pytest.mark.xfail(reason="BUG-006：券已标为 USED，接口却依然放行", strict=True)
def test_second_order_has_no_discount(user_a, db):
    """BUG-006：券状态已是 USED，第二单不该再有优惠金额"""
    order_with_coupon(user_a, 1, 1, user_coupon_id=2)

    with db.cursor() as cur:
        cur.execute("SELECT status FROM user_coupons WHERE id=2")
        assert cur.fetchone()[0] == "USED", "前提：第一单后券已被核销"

    _, body = order_with_coupon(user_a, 1, 1, user_coupon_id=2)
    discount = (body.get("data") or {}).get("discount_amount")
    assert discount == 0, "券已 USED，第二单不应再优惠，实际减了 %s 元" % discount
