# -*- coding: utf-8 -*-
"""缺陷复现 · 并发下单超卖

BUG-003 create_order 中「校验库存」与「扣减库存」分两步执行，
        中间没有加锁，多线程同时下单时会读到同一份旧库存，导致超卖。
"""
import threading

import pytest

pytestmark = pytest.mark.known_bug

RACERS = 30          # 并发用户数


@pytest.mark.xfail(reason="BUG-003 库存校验与扣减非原子操作", strict=False)
def test_bug003_concurrent_order_should_not_oversell(login, find_product, stock_of):
    """BUG-003 并发下单不应超卖。

    场景：库存 3 件的商品，30 个用户同时下单，每人 1 件。
    期望：最多 3 单成功，库存最终为 0 且不为负数
    实际：超过 3 单成功，库存被扣成负数
    """
    product = find_product("移动电源")           # 初始库存 3
    product_id = product["id"]

    clients = [login("racer%02d" % i) for i in range(RACERS)]

    # 加购环节串行执行，把干扰因素排除在并发窗口之外
    tickets = []
    for client in clients:
        resp = client.post("/api/cart/items", {"productId": product_id, "quantity": 1})
        assert resp.status == 200, resp.payload
        tickets.append((client, resp.data["cartId"]))

    results = []
    result_lock = threading.Lock()
    barrier = threading.Barrier(len(tickets))

    def place_order(client, cart_id):
        barrier.wait()                           # 所有线程对齐后同时发起请求
        resp = client.post("/api/orders", {"cartIds": [cart_id]})
        with result_lock:
            results.append(resp)

    threads = [threading.Thread(target=place_order, args=ticket) for ticket in tickets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    succeeded = [r for r in results if r.status == 200]
    remaining = stock_of(product_id)

    assert remaining >= 0, "库存被扣成负数：%d" % remaining
    assert len(succeeded) <= 3, \
        "库存仅 3 件，却成功下单 %d 笔（超卖 %d 件）" % (len(succeeded), len(succeeded) - 3)
