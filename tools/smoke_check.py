# -*- coding: utf-8 -*-
"""易淘商城 · 冒烟检查

不依赖 pytest，直接跑一遍主流程，用来确认服务是活的：

    python tools/smoke_check.py

流程：注册 -> 登录 -> 查商品 -> 加购物车 -> 下单 -> 支付 -> 查订单
"""
import io
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from sut import server as sut_server   # noqa: E402


def call(base, method, path, body=None, token=None):
    """发一次请求，返回 (状态码, 响应 dict)。"""
    url = base + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def main():
    httpd, base = sut_server.run_in_thread(0)
    print("服务已启动：%s\n" % base)

    steps = []

    st, r = call(base, "POST", "/api/user/register",
                 {"username": "smoke_user", "password": "abc123", "phone": "15576039320"})
    steps.append(("注册用户", st, r))
    uid = r.get("data", {}).get("userId")

    st, r = call(base, "POST", "/api/user/login",
                 {"username": "smoke_user", "password": "abc123"})
    steps.append(("登录", st, r))
    token = r.get("data", {}).get("token")

    st, r = call(base, "GET", "/api/products?page=1&size=3")
    steps.append(("查商品（第 1 页，3 条）", st, r))
    pid = r["data"]["items"][0]["id"]

    st, r = call(base, "POST", "/api/cart/items",
                 {"productId": pid, "quantity": 2}, token)
    steps.append(("加入购物车", st, r))
    cid = r.get("data", {}).get("cartId")

    st, r = call(base, "POST", "/api/orders", {"cartIds": [cid]}, token)
    steps.append(("提交订单", st, r))
    oid = r.get("data", {}).get("id")

    st, r = call(base, "POST", "/api/orders/%s/pay" % oid, {"payType": "ALIPAY"}, token)
    steps.append(("支付订单", st, r))

    st, r = call(base, "GET", "/api/orders/%s" % oid, token=token)
    steps.append(("查订单详情", st, r))

    print("-" * 68)
    ok = True
    for name, st, r in steps:
        flag = "OK " if st == 200 else "!! "
        if st != 200:
            ok = False
        print("%s%-24s HTTP %-4s %s" % (flag, name, st, json.dumps(r, ensure_ascii=False)[:88]))
    print("-" * 68)
    print("用户 ID：%s   订单 ID：%s   订单状态：%s"
          % (uid, oid, steps[-1][2].get("data", {}).get("status")))
    print("冒烟结果：%s" % ("全部通过" if ok else "存在失败，见上"))
    httpd.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
