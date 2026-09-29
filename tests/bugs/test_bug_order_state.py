# -*- coding: utf-8 -*-
"""缺陷复现 · 订单状态机

BUG-001 支付接口未校验订单状态，已取消的订单仍可支付成功
BUG-002 取消接口缺少幂等校验，重复取消会重复回滚库存
"""
import pytest

pytestmark = pytest.mark.known_bug


@pytest.mark.xfail(reason="BUG-001 支付接口未校验订单状态", strict=False)
def test_bug001_cancelled_order_should_not_be_payable(user_a, find_product, make_order):
    """BUG-001 已取消的订单不应还能支付成功。

    期望：支付已取消订单返回 400（订单状态非法）
    实际：返回 200，订单状态由 CANCELLED 变为 PAID
    """
    product = find_product("蓝牙耳机")
    _, order = make_order(user_a, product, 1)
    order_id = order.data["id"]

    cancelled = user_a.post("/api/orders/%s/cancel" % order_id)
    assert cancelled.data["status"] == "CANCELLED"

    resp = user_a.post("/api/orders/%s/pay" % order_id, {"payType": "ALIPAY"})
    assert resp.status == 400, "已取消订单竟然支付成功：%s" % resp.payload


@pytest.mark.xfail(reason="BUG-002 取消接口缺少幂等校验", strict=False)
def test_bug002_cancel_twice_should_not_restore_stock_twice(user_a, find_product,
                                                            make_order, stock_of):
    """BUG-002 重复取消同一订单不应重复回滚库存。

    期望：第二次取消被拒绝（或幂等返回），库存保持 50
    实际：返回 200，库存被重复释放为 52（凭空多出 2 件）
    """
    product = find_product("蓝牙耳机")          # 初始库存 50
    _, order = make_order(user_a, product, 2)
    order_id = order.data["id"]
    assert stock_of(product["id"]) == 48         # 下单后占用 2 件

    user_a.post("/api/orders/%s/cancel" % order_id)
    assert stock_of(product["id"]) == 50

    user_a.post("/api/orders/%s/cancel" % order_id)
    assert stock_of(product["id"]) == 50, \
        "重复取消导致库存虚增为 %d" % stock_of(product["id"])
