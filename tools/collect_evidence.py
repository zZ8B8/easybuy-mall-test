# -*- coding: utf-8 -*-
"""取证脚本：把三个缺陷的「实际观测值」原样抓出来，供文档引用。

用法（在项目根目录）：
    python tools/collect_evidence.py
"""
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sut import server as sut_server          # noqa: E402
from sut.store import store                   # noqa: E402
from tests.client import ApiClient            # noqa: E402


def new_client(base, username):
    api = ApiClient(base)
    api.post("/api/user/register",
             {"username": username, "password": "abc123", "phone": "15576039320"})
    token = api.post("/api/user/login",
                     {"username": username, "password": "abc123"}).data["token"]
    return ApiClient(base, token=token)


def find_product(base, keyword):
    for item in ApiClient(base).get("/api/products?page=1&size=50").data["items"]:
        if keyword in item["name"]:
            return item
    raise AssertionError(keyword)


def main():
    store.reset()
    httpd, base = sut_server.run_in_thread(port=0)
    out = []
    try:
        # ---------------- BUG-001 ----------------
        store.reset()
        alice = new_client(base, "alice")
        p = find_product(base, "蓝牙耳机")
        cart = alice.post("/api/cart/items",
                          {"productId": p["id"], "quantity": 1}).data["cartId"]
        oid = alice.post("/api/orders", {"cartIds": [cart]}).data["id"]
        alice.post("/api/orders/%s/cancel" % oid)
        st_after_cancel = alice.get("/api/orders/%s" % oid).data["status"]
        pay = alice.post("/api/orders/%s/pay" % oid, {"payType": "ALIPAY"})
        st_after_pay = alice.get("/api/orders/%s" % oid).data["status"]
        out.append(("BUG-001",
                    "取消后状态=%s" % st_after_cancel,
                    "支付已取消订单 HTTP=%d code=%s" % (pay.status, pay.data.get("code")),
                    "支付后状态=%s" % st_after_pay))

        # ---------------- BUG-002 ----------------
        store.reset()
        alice = new_client(base, "alice")
        p = find_product(base, "蓝牙耳机")
        stock0 = store.products[p["id"]]["stock"]
        cart = alice.post("/api/cart/items",
                          {"productId": p["id"], "quantity": 2}).data["cartId"]
        oid = alice.post("/api/orders", {"cartIds": [cart]}).data["id"]
        stock_after_order = store.products[p["id"]]["stock"]
        r1 = alice.post("/api/orders/%s/cancel" % oid)
        stock_after_cancel1 = store.products[p["id"]]["stock"]
        r2 = alice.post("/api/orders/%s/cancel" % oid)
        stock_after_cancel2 = store.products[p["id"]]["stock"]
        out.append(("BUG-002",
                    "初始库存=%d" % stock0,
                    "下单后=%d" % stock_after_order,
                    "第一次取消 HTTP=%d -> 库存=%d" % (r1.status, stock_after_cancel1),
                    "第二次取消 HTTP=%d -> 库存=%d（虚增 %d 件）"
                    % (r2.status, stock_after_cancel2, stock_after_cancel2 - stock0)))

        # ---------------- BUG-003 ----------------
        store.reset()
        p = find_product(base, "移动电源")
        stock0 = store.products[p["id"]]["stock"]
        n = 30
        clients = [new_client(base, "racer%02d" % i) for i in range(n)]
        tickets = []
        for c in clients:
            r = c.post("/api/cart/items", {"productId": p["id"], "quantity": 1})
            tickets.append((c, r.data["cartId"]))

        results = []
        lock = threading.Lock()
        barrier = threading.Barrier(len(tickets))

        def place(client, cart_id):
            barrier.wait()
            r = client.post("/api/orders", {"cartIds": [cart_id]})
            with lock:
                results.append(r)

        ts = [threading.Thread(target=place, args=t) for t in tickets]
        for t in ts:
            t.start()
        for t in ts:
            t.join()

        ok = [r for r in results if r.status == 200]
        fail = [r for r in results if r.status != 200]
        stock_end = store.products[p["id"]]["stock"]
        out.append(("BUG-003",
                    "初始库存=%d，并发用户=%d" % (stock0, n),
                    "下单成功=%d 笔，失败=%d 笔" % (len(ok), len(fail)),
                    "最终库存=%d" % stock_end))

        # ---------------- BUG-004 ----------------
        store.reset()
        alice = new_client(base, "alice")
        bob = new_client(base, "bob")
        p = find_product(base, "蓝牙耳机")
        cart = alice.post("/api/cart/items",
                          {"productId": p["id"], "quantity": 1}).data["cartId"]
        oid = alice.post("/api/orders", {"cartIds": [cart]}).data["id"]

        read = bob.get("/api/orders/%s" % oid)
        cancel = bob.post("/api/orders/%s/cancel" % oid)
        st = alice.get("/api/orders/%s" % oid).data["status"]
        out.append(("BUG-004",
                    "订单归属=alice，操作者=bob",
                    "bob 查 alice 订单 HTTP=%d code=%s" % (read.status, read.data.get("code")),
                    "bob 取消 alice 订单 HTTP=%d" % cancel.status,
                    "该订单最终状态=%s" % st))
    finally:
        httpd.shutdown()

    print("=" * 68)
    for row in out:
        print(row[0])
        for line in row[1:]:
            print("   " + line)
        print("-" * 68)


if __name__ == "__main__":
    main()
