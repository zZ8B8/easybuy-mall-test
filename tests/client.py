# -*- coding: utf-8 -*-
"""易淘商城 · 测试用 HTTP 客户端

标准库实现，不依赖 requests —— clone 下来装个 pytest 就能跑。

用法：
    c = ApiClient("http://127.0.0.1:5011")
    c.post("/api/user/login", {"username": "user_a", "password": "123456"})
    c.token = ...
    c.get("/api/cart/items")
"""
import json
import urllib.error
import urllib.parse
import urllib.request


class ApiClient(object):
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.token = None

    # ------------------------------------------------------------------
    def request(self, method, path, body=None, token=None):
        """发请求，返回 (status_code, json_dict)。"""
        headers = {"Content-Type": "application/json"}
        tk = token if token is not None else self.token
        if tk:
            headers["Authorization"] = "Bearer " + tk

        # 路径里可能有中文（比如 category=数码），必须编码后才能发出去
        url = self.base_url + urllib.parse.quote(path, safe="/?=&%#")

        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(raw)
            except ValueError:
                return exc.code, {"code": "NON_JSON", "message": raw}

    def get(self, path, token=None):
        return self.request("GET", path, None, token)

    def post(self, path, body=None, token=None):
        return self.request("POST", path, body, token)

    def put(self, path, body=None, token=None):
        return self.request("PUT", path, body, token)

    def delete(self, path, token=None):
        return self.request("DELETE", path, None, token)

    # ------------------------------------------------------------------
    # 常用业务动作，让用例写起来短一些
    # ------------------------------------------------------------------
    def login(self, username, password="123456"):
        status, body = self.post(
            "/api/user/login", {"username": username, "password": password}
        )
        assert status == 200 and body["code"] == "OK", "登录失败：%s" % body
        self.token = body["data"]["token"]
        return self.token

    def register(self, username, password="123456", phone=None):
        return self.post(
            "/api/user/register",
            {"username": username, "password": password, "phone": phone},
        )

    def add_to_cart(self, product_id, quantity=1):
        return self.post(
            "/api/cart/items", {"productId": product_id, "quantity": quantity}
        )

    def cart_items(self):
        status, body = self.get("/api/cart/items")
        assert status == 200, body
        return body["data"]["items"]

    def create_order(self, cart_ids):
        return self.post("/api/orders", {"cartIds": cart_ids})

    def pay(self, order_id, pay_type="ALIPAY"):
        return self.post("/api/orders/%s/pay" % order_id, {"payType": pay_type})

    def cancel(self, order_id):
        return self.post("/api/orders/%s/cancel" % order_id)

    def order(self, order_id):
        return self.get("/api/orders/%s" % order_id)

    def product(self, product_id):
        return self.get("/api/products/%s" % product_id)
