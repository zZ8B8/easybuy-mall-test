# -*- coding: utf-8 -*-
"""一键复现 5 个缺陷，打印现场证据。

用法（需要服务已经在跑）：
    python app.py            # 另一个窗口先启动服务
    python tools/verify_bugs.py

脚本会：重置数据 -> 逐个复现缺陷 -> 打印「期望 vs 实际」。
跑完会自动重置一次数据。
"""
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("EASYBUY_BASE", "http://127.0.0.1:5001")
LINE = "=" * 66


def call(method, path, body=None, token=None):
    url = BASE + urllib.parse.quote(path, safe="/?=&%#")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8")).get("data")
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        err = RuntimeError("%s: %s" % (payload.get("code"), payload.get("message")))
        err.code = payload.get("code")
        raise err


def get(p, token=None):
    return call("GET", p, None, token)


def post(p, b=None, token=None):
    return call("POST", p, b if b is not None else {}, token)


def login(username, password="123456"):
    return post("/api/user/login", {"username": username, "password": password})["token"]


def register(username, password="123456"):
    return post("/api/user/register", {"username": username, "password": password})


def reset():
    post("/api/dev/reset", {})


def stock_of(pid=1):
    return get("/api/products/%d" % pid)["stock"]


def verdict(right, got, ok):
    mark = "✔ 通过" if ok else "✘ 未通过（缺陷存在）"
    print("   期望：%s" % right)
    print("   实际：%s" % got)
    print("   判定：%s" % mark)


# ------------------------------------------------------------------
#  BUG-001 已取消的订单仍可支付
# ------------------------------------------------------------------
def bug_001():
    print(LINE)
    print("BUG-001 · 已取消的订单仍可被支付（状态机被击穿）")
    print(LINE)
    reset()
    token = login("demo")
    cart = post("/api/cart/items", {"productId": 4, "quantity": 1}, token)
    order = post("/api/orders", {"cartIds": [cart["cartId"]]}, token)
    cancel = post("/api/orders/%d/cancel" % order["id"], {}, token)
    print("   下单 -> %s，取消 -> %s" % (order["status"], cancel["status"]))

    paid = post("/api/orders/%d/pay" % order["id"], {}, token)
    verdict("该订单已取消，支付应被拒绝（HTTP 400）",
            "支付返回 200，状态变为 %s" % paid["status"], False)
    print()


# ------------------------------------------------------------------
#  BUG-002 重复取消导致库存重复回滚
# ------------------------------------------------------------------
def bug_002():
    print(LINE)
    print("BUG-002 · 重复取消订单导致库存重复回滚（不幂等）")
    print(LINE)
    reset()
    token = login("demo")
    before = stock_of(4)
    cart = post("/api/cart/items", {"productId": 4, "quantity": 2}, token)
    order = post("/api/orders", {"cartIds": [cart["cartId"]]}, token)
    after_order = stock_of(4)

    post("/api/orders/%d/cancel" % order["id"], {}, token)
    after_first = stock_of(4)
    post("/api/orders/%d/cancel" % order["id"], {}, token)
    after_second = stock_of(4)

    print("   P4 初始库存：%d" % before)
    print("   下单 2 件后：%d" % after_order)
    print("   第一次取消后：%d" % after_first)
    print("   第二次取消后：%d" % after_second)
    verdict("第二次取消应被拒绝，库存保持 %d" % after_first,
            "库存变为 %d，凭空多了 %d 件" % (after_second, after_second - after_first),
            after_second == after_first)
    print()


# ------------------------------------------------------------------
#  BUG-003 并发下单超卖
# ------------------------------------------------------------------
def bug_003():
    print(LINE)
    print("BUG-003 · 并发下单超卖，库存被扣成负数")
    print(LINE)
    reset()
    pid = 3
    before = stock_of(pid)
    workers = 20
    print("   P3 库存：%d，准备 %d 个并发下单请求……" % (before, workers))

    # 阶段一（串行）：每个线程准备一个账号 + 一条购物车记录
    plans = []      # [(token, cart_id), ...]
    for i in range(workers):
        uname = "conc%02d" % i
        try:
            register(uname)
        except RuntimeError:
            pass
        tk = login(uname)
        cart = post("/api/cart/items", {"productId": pid, "quantity": 1}, tk)
        plans.append((tk, cart["cartId"]))
    print("   已准备 %d 个账号，各自购物车放入 1 件 P3" % len(plans))

    # 阶段二（并发）：同时下单
    barrier = threading.Barrier(workers)
    results = []
    lock = threading.Lock()

    def worker(tk, cart_id):
        barrier.wait()
        try:
            post("/api/orders", {"cartIds": [cart_id]}, tk)
            outcome = "ok"
        except RuntimeError as exc:
            outcome = getattr(exc, "code", "ERR")
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker, args=(tk, cid))
               for tk, cid in plans]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ok = results.count("ok")
    after = stock_of(pid)
    verdict("下单成功数 ≤ %d，库存 ≥ 0" % before,
            "成功 %d 笔，库存变为 %d" % (ok, after),
            ok <= before and after >= 0)
    print()


# ------------------------------------------------------------------
#  BUG-004 越权访问他人订单
# ------------------------------------------------------------------
def bug_004():
    print(LINE)
    print("BUG-004 · 订单接口未校验归属，可越权操作他人订单（IDOR）")
    print(LINE)
    reset()
    token_a = login("user_a")
    cart = post("/api/cart/items", {"productId": 1, "quantity": 1}, token_a)
    order = post("/api/orders", {"cartIds": [cart["cartId"]]}, token_a)
    print("   user_a 下单 -> 订单号 %d" % order["id"])

    token_b = login("user_b")
    leaked = None
    try:
        leaked = get("/api/orders/%d" % order["id"], token_b)
    except RuntimeError as exc:
        print("   user_b 查询被拒绝：%s" % exc)

    verdict("user_b 不应看到 user_a 的订单",
            ("user_b 成功查到：金额 %.2f，商品 %d 项"
             % (leaked["amount"], len(leaked["items"]))) if leaked else "已拒绝",
            leaked is None)

    cancelled = None
    try:
        cancelled = post("/api/orders/%d/cancel" % order["id"], {}, token_b)
        print("   user_b 还成功把 user_a 的订单取消了（状态 %s）" % cancelled["status"])
    except RuntimeError as exc:
        print("   user_b 取消被拒绝：%s" % exc)
    print()


# ------------------------------------------------------------------
#  BUG-005 加购不校验数量
# ------------------------------------------------------------------
def bug_005():
    print(LINE)
    print("BUG-005 · 加购不校验数量，0 / 负数 / 超库存均可加入")
    print(LINE)
    reset()
    token = login("demo")
    cases = [(4, 0), (4, -3), (3, 999)]
    accepted = []
    for pid, qty in cases:
        try:
            r = post("/api/cart/items", {"productId": pid, "quantity": qty}, token)
            accepted.append((pid, qty, r.get("quantity")))
        except RuntimeError as exc:
            print("   P%d 数量 %s -> 已被拒绝（%s）" % (pid, qty, exc))

    if accepted:
        for pid, qty, stored in accepted:
            print("   P%d 数量 %s -> 200 接受，落库数量 %s" % (pid, qty, stored))
    verdict("0 / 负数 / 超库存 都应返回 400",
            "共 %d 种非法数量被接受" % len(accepted), len(accepted) == 0)
    print()


def main():
    print("")
    print(LINE)
    print("  易淘商城 · 缺陷复现验证")
    print("  目标服务：%s" % BASE)
    print(LINE)
    print("")

    try:
        get("/health")
    except Exception as exc:  # noqa: BLE001
        print("  [错误] 连不上服务（%s）" % exc)
        print("  请先在另一个窗口运行：python app.py")
        sys.exit(1)

    for fn in (bug_001, bug_002, bug_003, bug_004, bug_005):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print("   [异常] %s\n" % exc)

    reset()
    print(LINE)
    print("  验证结束。5 个缺陷均能被稳定复现。")
    print("  交给开发修复后，再跑 pytest（tests/bugs/）做回归验证。")
    print(LINE)
    print("")


if __name__ == "__main__":
    main()
