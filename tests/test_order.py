# -*- coding: utf-8 -*-
"""订单模块 · 功能测试

覆盖下单（含库存边界）、支付、取消、查询四组场景。
注意：涉及金额的断言只用能精确表示的数值（如 199.00 × 2），
浮点精度问题单独在 tests/bugs/ 中跟踪。
"""


class TestCreateOrder(object):
    """提交订单"""

    def test_create_success_and_stock_deducted(self, user_a, find_product,
                                               make_order, stock_of):
        """TC-ORDER-001 下单成功，订单为待支付且库存正确扣减"""
        product = find_product("蓝牙耳机")          # 库存 50
        _, resp = make_order(user_a, product, 2)
        assert resp.status == 200
        assert resp.data["status"] == "PENDING"
        assert resp.data["amount"] == 398.00
        assert resp.data["paid_at"] is None
        assert stock_of(product["id"]) == 48

    def test_insufficient_stock(self, user_a, find_product, add_cart):
        """TC-ORDER-002 库存不足时下单被拒绝（边界值：库存 3，下单 4）"""
        product = find_product("移动电源")          # 库存 3
        cart_id = add_cart(user_a, product, 4)
        resp = user_a.post("/api/orders", {"cartIds": [cart_id]})
        assert resp.status == 400
        assert resp.code == "INSUFFICIENT_STOCK"

    def test_stock_exactly_enough(self, user_a, find_product, make_order, stock_of):
        """TC-ORDER-003 下单数量恰好等于库存时成功，库存归零（边界值）"""
        product = find_product("移动电源")          # 库存 3
        _, resp = make_order(user_a, product, 3)
        assert resp.status == 200
        assert stock_of(product["id"]) == 0

    def test_cart_cleared_after_order(self, user_a, find_product, make_order):
        """TC-ORDER-004 下单成功后对应购物车条目被清除"""
        product = find_product("蓝牙耳机")
        make_order(user_a, product, 2)
        assert user_a.get("/api/cart/items").data["items"] == []

    def test_cart_not_found(self, user_a):
        """TC-ORDER-005 用不存在的购物车条目下单返回 404"""
        resp = user_a.post("/api/orders", {"cartIds": ["C99999"]})
        assert resp.status == 404
        assert resp.code == "CART_NOT_FOUND"

    def test_stock_unchanged_when_order_fails(self, user_a, find_product,
                                              add_cart, stock_of):
        """TC-ORDER-006 下单失败时库存不被扣减"""
        product = find_product("移动电源")          # 库存 3
        cart_id = add_cart(user_a, product, 9)
        user_a.post("/api/orders", {"cartIds": [cart_id]})
        assert stock_of(product["id"]) == 3


class TestPayOrder(object):
    """支付订单"""

    def test_pay_success(self, user_a, find_product, make_order):
        """TC-ORDER-007 支付成功，状态由 PENDING 流转为 PAID"""
        product = find_product("蓝牙耳机")
        _, order = make_order(user_a, product, 1)
        resp = user_a.post("/api/orders/%s/pay" % order.data["id"],
                           {"payType": "ALIPAY"})
        assert resp.status == 200
        assert resp.data["status"] == "PAID"
        assert resp.data["paid_at"] is not None
        assert resp.data["pay_type"] == "ALIPAY"

    def test_pay_invalid_type(self, user_a, find_product, make_order):
        """TC-ORDER-008 不支持的支付方式被拒绝"""
        product = find_product("蓝牙耳机")
        _, order = make_order(user_a, product, 1)
        resp = user_a.post("/api/orders/%s/pay" % order.data["id"],
                           {"payType": "BITCOIN"})
        assert resp.status == 400
        assert resp.code == "INVALID_PAY_TYPE"

    def test_pay_order_not_found(self, user_a):
        """TC-ORDER-009 支付不存在的订单返回 404"""
        resp = user_a.post("/api/orders/O99999/pay", {"payType": "ALIPAY"})
        assert resp.status == 404
        assert resp.code == "ORDER_NOT_FOUND"


class TestCancelOrder(object):
    """取消订单"""

    def test_cancel_releases_stock(self, user_a, find_product, make_order, stock_of):
        """TC-ORDER-010 取消订单后库存被释放回原值"""
        product = find_product("蓝牙耳机")          # 库存 50
        _, order = make_order(user_a, product, 2)
        assert stock_of(product["id"]) == 48
        resp = user_a.post("/api/orders/%s/cancel" % order.data["id"])
        assert resp.status == 200
        assert resp.data["status"] == "CANCELLED"
        assert stock_of(product["id"]) == 50

    def test_cancel_paid_order_rejected(self, user_a, find_product, make_order):
        """TC-ORDER-011 已支付订单不允许取消"""
        product = find_product("蓝牙耳机")
        _, order = make_order(user_a, product, 1)
        user_a.post("/api/orders/%s/pay" % order.data["id"], {"payType": "ALIPAY"})
        resp = user_a.post("/api/orders/%s/cancel" % order.data["id"])
        assert resp.status == 400
        assert resp.code == "ORDER_PAID"

    def test_cancel_not_found(self, user_a):
        """TC-ORDER-012 取消不存在的订单返回 404"""
        resp = user_a.post("/api/orders/O99999/cancel")
        assert resp.status == 404
        assert resp.code == "ORDER_NOT_FOUND"


class TestOrderQuery(object):
    """订单查询"""

    def test_detail_success(self, user_a, find_product, make_order):
        """TC-ORDER-013 查询订单详情返回明细"""
        product = find_product("蓝牙耳机")
        _, order = make_order(user_a, product, 2)
        resp = user_a.get("/api/orders/%s" % order.data["id"])
        assert resp.status == 200
        assert len(resp.data["items"]) == 1
        assert resp.data["items"][0]["quantity"] == 2
        assert resp.data["items"][0]["product_name"] == "无线蓝牙耳机"

    def test_detail_not_found(self, user_a):
        """TC-ORDER-014 订单不存在返回 404"""
        resp = user_a.get("/api/orders/O99999")
        assert resp.status == 404
        assert resp.code == "ORDER_NOT_FOUND"

    def test_list_only_mine(self, user_a, user_b, find_product, make_order):
        """TC-ORDER-015 订单列表只包含当前用户的订单"""
        product = find_product("蓝牙耳机")
        make_order(user_a, product, 1)
        make_order(user_a, product, 1)
        assert len(user_a.get("/api/orders").data["items"]) == 2
        assert user_b.get("/api/orders").data["items"] == []
