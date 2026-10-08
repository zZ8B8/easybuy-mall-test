# -*- coding: utf-8 -*-
"""购物车模块 · 接口测试

覆盖：加购（正常 / 累加 / 异常）、查询、改数量、删除、用户隔离
"""
import pytest


class TestCartAdd:

    def test_add_new_item(self, user_a):
        """正常：加入一件新商品"""
        status, body = user_a.add_to_cart(1, 2)
        assert status == 200
        assert body["code"] == "OK"
        assert body["data"]["quantity"] == 2

    def test_add_same_product_twice_accumulates(self, user_a):
        """等价类：同一商品重复加购，数量累加而不是新增一行"""
        user_a.add_to_cart(1, 2)
        user_a.add_to_cart(1, 3)
        items = user_a.cart_items()
        assert len(items) == 1, "同一商品应合并成一行"
        assert items[0]["quantity"] == 5

    def test_add_multiple_products(self, user_a):
        """等价类：加购多个不同商品"""
        user_a.add_to_cart(1, 1)
        user_a.add_to_cart(4, 1)
        assert len(user_a.cart_items()) == 2

    def test_add_product_not_exist(self, user_a):
        """异常场景：商品不存在 -> 404"""
        status, body = user_a.add_to_cart(99999, 1)
        assert status == 404
        assert body["code"] == "PRODUCT_NOT_FOUND"

    def test_add_without_quantity(self, user_a):
        """异常场景：缺少 quantity 字段"""
        status, body = user_a.post("/api/cart/items", {"productId": 1})
        assert status == 400
        assert body["code"] == "INVALID_PARAM"

    def test_add_requires_login(self, api):
        """异常场景：未登录不能加购"""
        status, body = api.add_to_cart(1, 1)
        assert status == 401

    def test_add_quantity_over_stock_accepted(self, user_a):
        """当前行为：加购数量超过库存也会被接受（库存校验在下单时做）

        见 BUG-005。这条用例锁定「现状」，等缺陷修复后应当改为断言 400。
        """
        status, body = user_a.add_to_cart(3, 999)     # 商品 3 库存只有 3
        assert status == 200, "当前实现不校验加购数量"


class TestCartQuery:

    def test_empty_cart(self, user_a):
        """边界-空：新用户的购物车是空的"""
        status, body = user_a.get("/api/cart/items")
        assert status == 200
        assert body["data"]["items"] == []

    def test_cart_item_fields(self, user_a):
        """正常：购物车行包含商品名、单价、库存等联表字段"""
        user_a.add_to_cart(2, 1)
        item = user_a.cart_items()[0]
        assert item["product_name"] == "机械键盘 87键"
        assert item["price"] == 329.5
        assert item["stock"] == 8


class TestCartUpdate:

    def test_update_quantity(self, user_a):
        """正常：修改数量"""
        user_a.add_to_cart(1, 1)
        cid = user_a.cart_items()[0]["id"]
        status, body = user_a.put("/api/cart/items/%s" % cid, {"quantity": 7})
        assert status == 200
        assert body["data"]["quantity"] == 7
        assert user_a.cart_items()[0]["quantity"] == 7

    def test_update_to_zero(self, user_a):
        """边界值：数量改成 0（当前实现允许）"""
        user_a.add_to_cart(1, 1)
        cid = user_a.cart_items()[0]["id"]
        status, body = user_a.put("/api/cart/items/%s" % cid, {"quantity": 0})
        assert status == 200
        assert body["data"]["quantity"] == 0

    def test_update_negative_quantity(self, user_a):
        """边界值：数量改成负数（当前实现允许）"""
        user_a.add_to_cart(1, 1)
        cid = user_a.cart_items()[0]["id"]
        status, body = user_a.put("/api/cart/items/%s" % cid, {"quantity": -5})
        assert status == 200
        assert body["data"]["quantity"] == -5

    def test_update_not_exist(self, user_a):
        """异常场景：购物车行不存在 -> 404"""
        status, body = user_a.put("/api/cart/items/99999", {"quantity": 1})
        assert status == 404
        assert body["code"] == "CART_NOT_FOUND"


class TestCartDelete:

    def test_delete_item(self, user_a):
        """正常：删除购物车行"""
        user_a.add_to_cart(1, 1)
        cid = user_a.cart_items()[0]["id"]
        status, body = user_a.delete("/api/cart/items/%s" % cid)
        assert status == 200
        assert user_a.cart_items() == []

    def test_delete_not_exist(self, user_a):
        """异常场景：删除不存在的行 -> 404"""
        status, body = user_a.delete("/api/cart/items/99999")
        assert status == 404

    def test_delete_twice(self, user_a):
        """幂等性：重复删除第二次应返回 404"""
        user_a.add_to_cart(1, 1)
        cid = user_a.cart_items()[0]["id"]
        assert user_a.delete("/api/cart/items/%s" % cid)[0] == 200
        assert user_a.delete("/api/cart/items/%s" % cid)[0] == 404


class TestCartIsolation:
    """购物车必须按用户隔离 —— 这是最基本的数据权限"""

    def test_cart_not_shared_between_users(self, user_a, user_b):
        """用户隔离：A 加购的商品不应出现在 B 的购物车里"""
        user_a.add_to_cart(1, 1)
        assert len(user_a.cart_items()) == 1
        assert user_b.cart_items() == []

    def test_cannot_update_others_cart(self, user_a, user_b):
        """越权防护：B 不能改 A 的购物车行"""
        user_a.add_to_cart(1, 1)
        cid = user_a.cart_items()[0]["id"]
        status, body = user_b.put("/api/cart/items/%s" % cid, {"quantity": 99})
        assert status == 404, "不应允许操作别人的购物车行"

    def test_cannot_delete_others_cart(self, user_a, user_b):
        """越权防护：B 不能删 A 的购物车行"""
        user_a.add_to_cart(1, 1)
        cid = user_a.cart_items()[0]["id"]
        status, body = user_b.delete("/api/cart/items/%s" % cid)
        assert status == 404
        assert len(user_a.cart_items()) == 1, "A 的购物车不应被删掉"
