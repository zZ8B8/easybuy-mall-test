# -*- coding: utf-8 -*-
"""用户模块 · 功能测试

覆盖注册、登录、鉴权三类场景，全部用例均应通过。
用例编号与 docs/测试用例.md 一一对应。
"""
import pytest


class TestRegister(object):
    """注册"""

    def test_register_success(self, api):
        """TC-USER-001 正常注册成功"""
        resp = api.post("/api/user/register", {
            "username": "alice", "password": "abc123", "phone": "15576039320"})
        assert resp.status == 200
        assert resp.code == "OK"
        assert resp.data["username"] == "alice"
        assert resp.data["userId"].startswith("U")

    def test_register_duplicate_username(self, api):
        """TC-USER-002 用户名重复注册被拒绝"""
        body = {"username": "alice", "password": "abc123", "phone": "15576039320"}
        assert api.post("/api/user/register", body).status == 200
        resp = api.post("/api/user/register", body)
        assert resp.status == 400
        assert resp.code == "USER_EXISTS"

    @pytest.mark.parametrize("password,expect_len", [
        ("", 0), ("12345", 5), ("a", 1),
    ])
    def test_register_password_too_short(self, api, password, expect_len):
        """TC-USER-003 密码长度不足 6 位被拒绝（边界值：0 / 5 / 1）"""
        resp = api.post("/api/user/register", {
            "username": "u%s" % expect_len, "password": password, "phone": "15576039320"})
        assert resp.status == 400
        assert resp.code in ("WEAK_PASSWORD", "INVALID_PARAM")

    @pytest.mark.parametrize("phone", ["123", "155760393201", "1557603932a"])
    def test_register_invalid_phone(self, api, phone):
        """TC-USER-004 手机号格式非法被拒绝（边界值：过短 / 过长 / 含字母）"""
        resp = api.post("/api/user/register", {
            "username": "phone_case", "password": "abc123", "phone": phone})
        assert resp.status == 400
        assert resp.code == "INVALID_PHONE"

    def test_register_empty_username(self, api):
        """TC-USER-005 用户名为空被拒绝"""
        resp = api.post("/api/user/register", {
            "username": "", "password": "abc123", "phone": "15576039320"})
        assert resp.status == 400
        assert resp.code == "INVALID_PARAM"


class TestLogin(object):
    """登录"""

    def test_login_success(self, api):
        """TC-USER-006 正确账号密码登录成功并返回 token"""
        api.post("/api/user/register", {
            "username": "alice", "password": "abc123", "phone": "15576039320"})
        resp = api.post("/api/user/login", {"username": "alice", "password": "abc123"})
        assert resp.status == 200
        assert resp.data["token"].startswith("T")

    def test_login_wrong_password(self, api):
        """TC-USER-007 密码错误返回 401"""
        api.post("/api/user/register", {
            "username": "alice", "password": "abc123", "phone": "15576039320"})
        resp = api.post("/api/user/login", {"username": "alice", "password": "wrong!"})
        assert resp.status == 401
        assert resp.code == "LOGIN_FAILED"

    def test_login_unknown_user(self, api):
        """TC-USER-008 不存在的用户返回 401"""
        resp = api.post("/api/user/login", {"username": "nobody", "password": "abc123"})
        assert resp.status == 401
        assert resp.code == "LOGIN_FAILED"


class TestAuth(object):
    """鉴权"""

    def test_cart_requires_token(self, api):
        """TC-USER-009 未携带 token 访问购物车返回 401"""
        resp = api.get("/api/cart/items")
        assert resp.status == 401
        assert resp.code == "UNAUTHORIZED"

    def test_invalid_token_rejected(self, api):
        """TC-USER-010 伪造 token 被拒绝"""
        resp = api.get("/api/cart/items", token="T99999")
        assert resp.status == 401
        assert resp.code == "UNAUTHORIZED"
