# -*- coding: utf-8 -*-
"""缺陷复现 · 水平越权

BUG-004 订单详情查询与取消接口都只校验「是否登录」，不校验「是否为本人订单」。
        任意登录用户只要拿到订单号，就能查看甚至取消别人的订单。
"""
import pytest

pytestmark = pytest.mark.known_bug


@pytest.mark.xfail(reason="BUG-004 订单接口未做归属校验", strict=False)
def test_bug004_cannot_read_others_order(user_a, user_b, find_product, make_order):
    """BUG-004 用户 B 不应能查看用户 A 的订单详情。

    期望：返回 403（无权访问）或 404（不可见）
    实际：返回 200，并把 A 的订单明细、金额完整返回给 B
    """
    product = find_product("蓝牙耳机")
    _, order = make_order(user_a, product, 1)
    order_id = order.data["id"]

    resp = user_b.get("/api/orders/%s" % order_id)
    assert resp.status in (403, 404), \
        "越权读到他人订单：HTTP=%d 内容=%s" % (resp.status, resp.payload)


@pytest.mark.xfail(reason="BUG-004 订单接口未做归属校验", strict=False)
def test_bug004_cannot_cancel_others_order(user_a, user_b, find_product,
                                           make_order, stock_of):
    """BUG-004 用户 B 不应能取消用户 A 的订单。

    期望：返回 403 / 404，A 的订单状态保持 PENDING、库存不动
    实际：返回 200，A 的订单被 B 取消，库存被释放
    """
    product = find_product("蓝牙耳机")
    stock_before = stock_of(product["id"])

    _, order = make_order(user_a, product, 2)
    order_id = order.data["id"]
    stock_after_order = stock_of(product["id"])
    assert stock_after_order == stock_before - 2

    resp = user_b.post("/api/orders/%s/cancel" % order_id)
    assert resp.status in (403, 404), \
        "越权取消他人订单：HTTP=%d" % resp.status

    still = user_a.get("/api/orders/%s" % order_id)
    assert still.data["status"] == "PENDING", \
        "A 的订单被 B 改成了 %s" % still.data["status"]
