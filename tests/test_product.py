# -*- coding: utf-8 -*-
"""商品模块 · 接口测试

覆盖：列表分页（边界值）、分类过滤（等价类）、详情（异常场景）
"""
import pytest


class TestProductList:

    def test_list_default(self, api):
        """正常：默认返回第 1 页，共 6 件商品"""
        status, body = api.get("/api/products")
        assert status == 200
        assert body["code"] == "OK"
        assert body["data"]["total"] == 6
        assert body["data"]["page"] == 1
        assert len(body["data"]["items"]) == 6

    @pytest.mark.parametrize("size,expected", [(1, 1), (3, 3), (6, 6)])
    def test_list_page_size(self, api, size, expected):
        """边界值：每页条数 1 / 3 / 6"""
        status, body = api.get("/api/products?page=1&size=%d" % size)
        assert status == 200
        assert len(body["data"]["items"]) == expected

    def test_list_second_page(self, api):
        """正常：第 2 页应有数据且与第 1 页不重复"""
        _, p1 = api.get("/api/products?page=1&size=3")
        _, p2 = api.get("/api/products?page=2&size=3")
        ids1 = [i["id"] for i in p1["data"]["items"]]
        ids2 = [i["id"] for i in p2["data"]["items"]]
        assert len(ids2) == 3
        assert set(ids1).isdisjoint(set(ids2))

    def test_list_page_beyond_range(self, api):
        """边界-越界：请求远超实际页码，应返回空列表而不是报错"""
        status, body = api.get("/api/products?page=999&size=10")
        assert status == 200
        assert body["data"]["items"] == []
        assert body["data"]["total"] == 6

    def test_list_size_larger_than_total(self, api):
        """边界-越界：size 大于总数，返回全部"""
        status, body = api.get("/api/products?size=100")
        assert status == 200
        assert len(body["data"]["items"]) == 6

    @pytest.mark.parametrize("category,count", [("数码", 3), ("服饰", 2), ("食品", 1)])
    def test_list_filter_by_category(self, api, category, count):
        """等价类：按分类过滤"""
        status, body = api.get("/api/products?category=%s" % category)
        assert status == 200
        assert body["data"]["total"] == count
        assert all(i["category"] == category for i in body["data"]["items"])

    def test_list_filter_unknown_category(self, api):
        """等价类-无效：不存在的分类 -> 空结果"""
        status, body = api.get("/api/products?category=不存在的分类")
        assert status == 200
        assert body["data"]["total"] == 0
        assert body["data"]["items"] == []

    def test_list_field_completeness(self, api):
        """正常：返回字段完整且类型正确"""
        _, body = api.get("/api/products?size=1")
        item = body["data"]["items"][0]
        for field in ("id", "name", "category", "price", "stock", "status"):
            assert field in item, "缺少字段 %s" % field
        assert isinstance(item["price"], (int, float))
        assert isinstance(item["stock"], int)

    def test_list_price_precision(self, api):
        """金额精度：机械键盘 329.50，不能变成 329.5 之外的值"""
        _, body = api.get("/api/products/2")
        assert body["data"]["price"] == 329.5


class TestProductDetail:

    @pytest.mark.parametrize(
        "pid,name,price,stock",
        [
            (1, "无线蓝牙耳机", 199.0, 50),
            (2, "机械键盘 87键", 329.5, 8),
            (3, "移动电源 20000mAh", 129.0, 3),
            (4, "纯棉短袖T恤", 59.9, 100),
            (5, "经典帆布鞋", 189.0, 20),
            (6, "每日坚果礼盒 750g", 99.99, 5),
        ],
    )
    def test_detail_all_products(self, api, pid, name, price, stock):
        """等价类：6 件商品的详情逐一校验（数据驱动）"""
        status, body = api.get("/api/products/%d" % pid)
        assert status == 200
        d = body["data"]
        assert d["name"] == name
        assert d["price"] == price
        assert d["stock"] == stock
        assert d["status"] == "ON_SALE"

    def test_detail_not_found(self, api):
        """异常场景：商品不存在 -> 404"""
        status, body = api.get("/api/products/99999")
        assert status == 404
        assert body["code"] == "PRODUCT_NOT_FOUND"

    def test_detail_non_numeric_id(self, api):
        """异常场景：商品 ID 不是数字 -> 404（路由不匹配）"""
        status, body = api.get("/api/products/abc")
        assert status == 404

    def test_detail_negative_id(self, api):
        """边界-无效：负数 ID"""
        status, body = api.get("/api/products/-1")
        assert status == 404

    def test_detail_zero_id(self, api):
        """边界值：ID = 0（自增主键从 1 开始，0 不存在）"""
        status, body = api.get("/api/products/0")
        assert status == 404


class TestHealth:

    def test_health(self, api):
        """健康检查：服务与数据库都正常"""
        status, body = api.get("/health")
        assert status == 200
        assert body["data"]["status"] == "UP"
        assert body["data"]["db"]
