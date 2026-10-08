# -*- coding: utf-8 -*-
"""BUG-001 · 已取消的订单仍然可以支付成功

缺陷类型：状态机缺陷
严重级别：高
根因：pay_order() 直接改状态，没有先校验订单当前状态。
      订单状态机本应是 PENDING -> PAID / CANCELLED 的单向流动，
      现在 CANCELLED -> PAID 也被放行了。

影响：已取消的订单（库存已经回滚）还能被支付，造成
      「钱收了、货没扣库存」的对不上账。
"""
import pytest


@pytest.mark.xfail(reason="BUG-001：pay_order 缺少订单状态校验", strict=True)
def test_cancelled_order_can_still_be_paid(user_a):
    """已取消的订单，再次支付应当被拒绝（400）"""
    user_a.add_to_cart(1, 1)
    cid = user_a.cart_items()[0]["id"]
    order_id = user_a.create_order([cid])[1]["data"]["id"]

    # 先取消
    status, body = user_a.cancel(order_id)
    assert body["data"]["status"] == "CANCELLED"

    # 再支付 —— 期望被拒绝，实际成功了
    status, body = user_a.pay(order_id)
    assert status == 400, (
        "已取消的订单不应能支付，但服务端返回 %s，订单状态变成了 %s"
        % (status, body["data"]["status"])
    )


@pytest.mark.xfail(reason="BUG-001：pay_order 缺少订单状态校验", strict=True)
def test_cancelled_order_status_persisted_as_paid(user_a, db):
    """从数据库侧确认：取消后的订单状态真的被改成了 PAID"""
    user_a.add_to_cart(1, 1)
    cid = user_a.cart_items()[0]["id"]
    order_id = user_a.create_order([cid])[1]["data"]["id"]

    user_a.cancel(order_id)
    user_a.pay(order_id)

    with db.cursor() as cur:
        cur.execute("SELECT status FROM orders WHERE id = %s", (order_id,))
        status = cur.fetchone()[0]

    assert status != "PAID", (
        "订单 %s 已被取消，却被支付改写成了 %s —— 状态机被打穿" % (order_id, status)
    )
