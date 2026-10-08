# -*- coding: utf-8 -*-
"""用户模块 · 接口测试

覆盖：注册（等价类 + 边界）、登录（等价类）、鉴权（异常场景）
"""
import uuid

import pytest


def uniq(prefix="u"):
    return "%s_%s" % (prefix, uuid.uuid4().hex[:8])


# ======================================================================
# 注册
# ======================================================================
class TestRegister:

    def test_register_success(self, api):
        """正常注册：返回用户 ID 和用户名"""
        name = uniq()
        status, body = api.register(name, "abc123", "13800001111")
        assert status == 200
        assert body["code"] == "OK"
        assert body["data"]["username"] == name
        assert isinstance(body["data"]["userId"], int)

    def test_register_duplicate_username(self, api):
        """等价类-无效：用户名已存在"""
        status, body = api.register("user_a", "123456")
        assert status == 400
        assert body["code"] == "USERNAME_EXISTS"
        assert "已被占用" in body["message"]

    def test_register_empty_username(self, api):
        """边界-空值：用户名为空字符串"""
        status, body = api.register("", "123456")
        assert status == 400
        assert body["code"] == "INVALID_PARAM"

    def test_register_blank_username(self, api):
        """边界-空值：用户名只有空格（应被 strip 后判空）"""
        status, body = api.register("   ", "123456")
        assert status == 400
        assert body["code"] == "INVALID_PARAM"

    def test_register_missing_password(self, api):
        """边界-空值：密码为空"""
        status, body = api.register(uniq(), "")
        assert status == 400
        assert body["code"] == "INVALID_PARAM"

    def test_register_without_phone(self, api):
        """等价类：手机号是选填项"""
        status, body = api.register(uniq(), "123456")
        assert status == 200
        assert body["code"] == "OK"

    def test_register_username_trimmed(self, api):
        """等价类：用户名前后的空格应被去掉"""
        name = uniq()
        status, body = api.register("  %s  " % name, "123456")
        assert status == 200
        assert body["data"]["username"] == name

    @pytest.mark.parametrize("length", [1, 50])
    def test_register_username_length_boundary(self, api, length):
        """边界值：用户名长度 1 和 50（字段上限）"""
        name = "a" * length
        status, body = api.register(name, "123456")
        assert status == 200, "长度 %d 应当可以注册：%s" % (length, body)


# ======================================================================
# 登录
# ======================================================================
class TestLogin:

    def test_login_success(self, api):
        """正常登录：返回 token"""
        status, body = api.post(
            "/api/user/login", {"username": "user_a", "password": "123456"}
        )
        assert status == 200
        assert body["code"] == "OK"
        assert len(body["data"]["token"]) == 32

    def test_login_wrong_password(self, api):
        """等价类-无效：密码错误 -> 401"""
        status, body = api.post(
            "/api/user/login", {"username": "user_a", "password": "wrong"}
        )
        assert status == 401
        assert body["code"] == "LOGIN_FAILED"

    def test_login_user_not_exist(self, api):
        """等价类-无效：用户不存在，错误码与密码错误一致（不泄露账号是否存在）"""
        status, body = api.post(
            "/api/user/login", {"username": "no_such_user", "password": "123456"}
        )
        assert status == 401
        assert body["code"] == "LOGIN_FAILED"

    def test_login_empty_password(self, api):
        """边界-空值：密码为空"""
        status, body = api.post(
            "/api/user/login", {"username": "user_a", "password": ""}
        )
        assert status == 401

    def test_login_missing_body(self, api):
        """异常场景：完全不传请求体"""
        status, body = api.post("/api/user/login", {})
        assert status == 401

    def test_login_twice_gets_different_token(self, api):
        """等价类：两次登录得到不同的 token（各自独立会话）"""
        _, b1 = api.post("/api/user/login", {"username": "user_a", "password": "123456"})
        _, b2 = api.post("/api/user/login", {"username": "user_a", "password": "123456"})
        assert b1["data"]["token"] != b2["data"]["token"]

    def test_old_token_still_valid_after_new_login(self, api):
        """等价类：新登录不应让旧 token 失效（当前设计为多端共存）"""
        _, b1 = api.post("/api/user/login", {"username": "user_a", "password": "123456"})
        token1 = b1["data"]["token"]
        api.post("/api/user/login", {"username": "user_a", "password": "123456"})

        status, body = api.get("/api/user/profile", token=token1)
        assert status == 200
        assert body["code"] == "OK"
        assert body["data"]["username"] == "user_a"


# ======================================================================
# 鉴权
# ======================================================================
class TestAuth:

    def test_profile_without_token(self, api):
        """异常场景：不带 token 访问需要登录的接口"""
        status, body = api.get("/api/user/profile")
        assert status == 401
        assert body["code"] == "UNAUTHORIZED"

    def test_profile_with_fake_token(self, api):
        """异常场景：伪造 token"""
        status, body = api.get("/api/user/profile", token="fake_token_1234567890")
        assert status == 401
        assert body["code"] == "UNAUTHORIZED"

    def test_profile_with_empty_token(self, api):
        """边界-空值：Authorization 头为空"""
        status, body = api.get("/api/user/profile", token="")
        assert status == 401

    def test_profile_with_valid_token(self, user_a):
        """正常场景：带有效 token"""
        status, body = user_a.get("/api/user/profile")
        assert status == 200
        assert body["data"]["username"] == "user_a"

    @pytest.mark.parametrize(
        "path", ["/api/cart/items", "/api/orders", "/api/user/profile"]
    )
    def test_protected_endpoints_require_auth(self, api, path):
        """等价类：所有需要登录的接口，未登录都应返回 401"""
        status, body = api.get(path)
        assert status == 401
        assert body["code"] == "UNAUTHORIZED"
