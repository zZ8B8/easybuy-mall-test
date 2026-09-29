# -*- coding: utf-8 -*-
"""商品模块 · 功能测试

重点覆盖分页边界与分类筛选。
"""
from urllib.parse import quote


class TestProductList(object):
    """商品列表 / 分页"""

    def test_default_page(self, api):
        """TC-PROD-001 默认分页返回全部商品"""
        resp = api.get("/api/products?page=1&size=10")
        assert resp.status == 200
        assert resp.code == "OK"
        assert resp.data["total"] == 6
        assert len(resp.data["items"]) == 6

    def test_pagination_first_page(self, api):
        """TC-PROD-002 第 1 页取 3 条，从第一条开始"""
        resp = api.get("/api/products?page=1&size=3")
        assert len(resp.data["items"]) == 3
        assert resp.data["items"][0]["id"] == "P00001"

    def test_pagination_no_overlap(self, api):
        """TC-PROD-003 相邻两页数据不重复"""
        p1 = api.get("/api/products?page=1&size=3").data["items"]
        p2 = api.get("/api/products?page=2&size=3").data["items"]
        assert len(p1) == 3 and len(p2) == 3
        assert not set(i["id"] for i in p1) & set(i["id"] for i in p2)

    def test_last_page_partial(self, api):
        """TC-PROD-004 末页不足一页时按实际条数返回（6 条取 size=5）"""
        resp = api.get("/api/products?page=2&size=5")
        assert len(resp.data["items"]) == 1

    def test_page_beyond_range(self, api):
        """TC-PROD-005 超出范围的分页返回空列表，不报错"""
        resp = api.get("/api/products?page=99&size=10")
        assert resp.status == 200
        assert resp.data["items"] == []

    def test_filter_by_category(self, api):
        """TC-PROD-006 按分类筛选只返回该分类商品"""
        resp = api.get("/api/products?page=1&size=10&category=%s" % quote("数码"))
        assert resp.data["total"] == 3
        assert all(i["category"] == "数码" for i in resp.data["items"])

    def test_page_size_one(self, api):
        """TC-PROD-007 size=1 的极限分页"""
        resp = api.get("/api/products?page=1&size=1")
        assert len(resp.data["items"]) == 1
        assert resp.data["total"] == 6


class TestProductDetail(object):
    """商品详情"""

    def test_detail_success(self, api):
        """TC-PROD-008 查询商品详情返回完整字段"""
        resp = api.get("/api/products/P00001")
        assert resp.status == 200
        assert resp.data["name"] == "无线蓝牙耳机"
        assert resp.data["price"] == 199.00
        assert resp.data["stock"] == 50
        assert resp.data["status"] == "ON_SALE"

    def test_detail_not_found(self, api):
        """TC-PROD-009 商品不存在返回 404"""
        resp = api.get("/api/products/P99999")
        assert resp.status == 404
        assert resp.code == "PRODUCT_NOT_FOUND"
