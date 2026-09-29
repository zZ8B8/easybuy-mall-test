# -*- coding: utf-8 -*-
"""pytest 公共装置（fixture）

- 整个测试会话共用一个 HTTP 服务实例（随机空闲端口）；
- 每个用例开始前重置内存数据，用例之间互不污染；
- 提供「已注册并登录」的客户端，省掉每个用例重复写注册/登录。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sut import server as sut_server          # noqa: E402
from sut.store import store                   # noqa: E402
from tests.client import ApiClient            # noqa: E402


@pytest.fixture(scope="session")
def api_base():
    """启动服务，会话结束后关闭。port=0 由系统分配空闲端口。"""
    httpd, base_url = sut_server.run_in_thread(port=0)
    yield base_url
    httpd.shutdown()


@pytest.fixture(autouse=True)
def fresh_data():
    """每个用例前清空数据并重新预置商品。"""
    store.reset()
    yield


@pytest.fixture
def api(api_base):
    """未登录的客户端。"""
    return ApiClient(api_base)


@pytest.fixture
def login(api):
    """注册 + 登录，返回已带 token 的客户端。

        def test_x(login):
            alice = login("alice")
    """
    def _login(username, password="abc123", phone=None):
        api.post("/api/user/register",
                 {"username": username, "password": password, "phone": phone})
        resp = api.post("/api/user/login",
                        {"username": username, "password": password})
        assert resp.status == 200, "登录失败：%s" % resp.payload
        return ApiClient(api.base_url, token=resp.data["token"])

    return _login


@pytest.fixture
def user_a(login):
    """默认用户 alice。"""
    return login("alice")


@pytest.fixture
def user_b(login):
    """默认用户 bob（用于越权类用例）。"""
    return login("bob")


@pytest.fixture
def find_product(api):
    """按名称片段查商品，返回商品对象。避免用例硬编码商品 ID。"""
    def _find(keyword):
        resp = api.get("/api/products?page=1&size=50")
        assert resp.status == 200, resp.payload
        for item in resp.data["items"]:
            if keyword in item["name"]:
                return item
        raise AssertionError("找不到商品：%s" % keyword)

    return _find


@pytest.fixture
def stock_of():
    """读取某商品当前库存（直接读内存，不经 HTTP）。"""
    def _stock(product_id):
        return store.products[product_id]["stock"]

    return _stock


@pytest.fixture
def add_cart():
    """把商品加入购物车，返回 cart_id。"""
    def _add(client, product, quantity=1):
        resp = client.post("/api/cart/items",
                           {"productId": product["id"], "quantity": quantity})
        assert resp.status == 200, "加购失败：%s" % resp.payload
        return resp.data["cartId"]

    return _add


@pytest.fixture
def make_order(add_cart):
    """加购并下单，返回 (cart_id, 下单响应)。"""
    def _make(client, product, quantity=1):
        cart_id = add_cart(client, product, quantity)
        return cart_id, client.post("/api/orders", {"cartIds": [cart_id]})

    return _make
