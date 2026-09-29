# -*- coding: utf-8 -*-
"""购物车模块 · 功能测试

覆盖加购、累加、改数量、删除，以及不同用户之间的数据隔离。
"""
import pytest


class TestCartAdd(object):
    """加入购物车"""

    def test_add_success(self, user_a, find_product):
        """TC-CART-001 加入购物车成功"""
        product = find_product("蓝牙耳机")
        resp = user_a.post("/api/cart/items",
                           {"productId": product["id"], "quantity": 2})
        assert resp.status == 200
        assert resp.data["quantity"] == 2

    def test_add_same_product_accumulates(self, user_a, find_product):
        """TC-CART-002 同一商品重复加购数量累加"""
        product = find_product("蓝牙耳机")
        user_a.post("/api/cart/items", {"productId": product["id"], "quantity": 2})
        resp = user_a.post("/api/cart/items", {"productId": product["id"], "quantity": 3})
        assert resp.data["quantity"] == 5
        assert len(user_a.get("/api/cart/items").data["items"]) == 1

    def test_add_unknown_product(self, user_a):
        """TC-CART-003 加入不存在的商品返回 404"""
        resp = user_a.post("/api/cart/items", {"productId": "P99999", "quantity": 1})
        assert resp.status == 404
        assert resp.code == "PRODUCT_NOT_FOUND"

    def test_cart_isolated_between_users(self, user_a, user_b, find_product):
        """TC-CART-004 用户之间购物车数据互不可见"""
        product = find_product("蓝牙耳机")
        user_a.post("/api/cart/items", {"productId": product["id"], "quantity": 2})
        assert user_b.get("/api/cart/items").data["items"] == []

    def test_cart_item_contains_product_snapshot(self, user_a, find_product):
        """TC-CART-005 购物车条目带商品名称与单价快照"""
        product = find_product("蓝牙耳机")
        user_a.post("/api/cart/items", {"productId": product["id"], "quantity": 1})
        item = user_a.get("/api/cart/items").data["items"][0]
        assert item["product_name"] == "无线蓝牙耳机"
        assert item["price"] == 199.00


class TestCartManage(object):
    """购物车条目管理"""

    def test_update_quantity(self, user_a, find_product):
        """TC-CART-006 修改购物车数量生效"""
        product = find_product("蓝牙耳机")
        cart_id = user_a.post("/api/cart/items",
                              {"productId": product["id"], "quantity": 2}).data["cartId"]
        resp = user_a.put("/api/cart/items/%s" % cart_id, {"quantity": 7})
        assert resp.status == 200
        assert resp.data["quantity"] == 7

    def test_update_unknown_item(self, user_a):
        """TC-CART-007 修改不存在的条目返回 404"""
        resp = user_a.put("/api/cart/items/C99999", {"quantity": 1})
        assert resp.status == 404
        assert resp.code == "CART_NOT_FOUND"

    def test_remove_item(self, user_a, find_product):
        """TC-CART-008 删除条目后购物车为空"""
        product = find_product("蓝牙耳机")
        cart_id = user_a.post("/api/cart/items",
                              {"productId": product["id"], "quantity": 2}).data["cartId"]
        assert user_a.delete("/api/cart/items/%s" % cart_id).status == 200
        assert user_a.get("/api/cart/items").data["items"] == []

    def test_remove_unknown_item(self, user_a):
        """TC-CART-009 删除不存在的条目返回 404"""
        resp = user_a.delete("/api/cart/items/C99999")
        assert resp.status == 404
        assert resp.code == "CART_NOT_FOUND"

    @pytest.mark.parametrize("cart_ids,expected", [
        ([], "EMPTY_CART"),
    ])
    def test_order_requires_at_least_one_item(self, user_a, cart_ids, expected):
        """TC-CART-010 购物车为空时不能下单"""
        resp = user_a.post("/api/orders", {"cartIds": cart_ids})
        assert resp.status == 400
        assert resp.code == expected
