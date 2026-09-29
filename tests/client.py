# -*- coding: utf-8 -*-
"""极简 HTTP 测试客户端（标准库实现，不依赖 requests）

让测试只关注业务断言，不用重复写 urllib 的样板代码。
"""
import json
import urllib.error
import urllib.request


class ApiResponse(object):
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    @property
    def code(self):
        """业务码：成功为 "OK"，失败为错误码。"""
        return self.payload.get("code")

    @property
    def message(self):
        return self.payload.get("message")

    @property
    def data(self):
        return self.payload.get("data")

    def __repr__(self):
        return "<ApiResponse %s %s>" % (self.status, json.dumps(self.payload, ensure_ascii=False))


class ApiClient(object):
    """带 token 的接口客户端。"""

    def __init__(self, base_url, token=None):
        self.base_url = base_url
        self.token = token

    def request(self, method, path, body=None, token=None, timeout=15):
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.base_url + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        use_token = token if token is not None else self.token
        if use_token:
            req.add_header("Authorization", "Bearer " + use_token)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return ApiResponse(resp.status, json.loads(resp.read().decode("utf-8")))
        except urllib.error.HTTPError as e:
            return ApiResponse(e.code, json.loads(e.read().decode("utf-8")))

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body, **kw)

    def put(self, path, body=None, **kw):
        return self.request("PUT", path, body, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    def with_token(self, token):
        """返回一个共享同一服务、但使用指定 token 的新客户端。"""
        return ApiClient(self.base_url, token)
