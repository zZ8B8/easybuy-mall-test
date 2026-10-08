# -*- coding: utf-8 -*-
"""BUG-003 · 并发下单超卖

缺陷类型：并发 / 竞态条件（读-校验-写 非原子）
严重级别：严重
根因：create_order() 里「校验库存」和「扣减库存」是两次独立的数据库操作，
      中间没有任何锁或原子保证。

      并发时序：
        T1 读到库存 3 -> 通过校验
        T2 读到库存 3 -> 通过校验      <- 还没人扣减
        T3 读到库存 3 -> 通过校验
        ...
        T1 扣减 -> 2
        T2 扣减 -> 1
        T3 扣减 -> 0
        T4 扣减 -> -1                  <- 卖超了

影响：库存变成负数，超卖。电商最严重的一类线上事故。

修复方向（任选）：
    1) 原子扣减：UPDATE products SET stock = stock - %s
                 WHERE id = %s AND stock >= %s，看 affected_rows 判断成败
    2) 悲观锁：SELECT ... FOR UPDATE，把校验和扣减放进同一个事务
    3) 乐观锁：加版本号字段

关于「竞态窗口」
----------------
竞态缺陷天生是概率性的。本机数据库就在同机、内存命中，窗口小到
跑十次才中一次 —— 这样的用例没法进回归测试（时绿时红）。

所以这里做两件事：
    · 服务端在「校验」和「扣减」之间留出一段显式延迟
      （config.SIMULATE_DB_LATENCY，模拟真实系统的网络往返）
    · 用例里再把这段延迟放大到 0.3 秒，并让 20 个线程在同一道闸门后出发

这样缺陷从「偶现」变成「必现」，才配得上写进回归测试。
"""
import threading

import pytest

import config
from tests.client import ApiClient
from tests.conftest import BASE_URL, stock_of

CONCURRENCY = 20          # 并发线程数
PRODUCT_ID = 3            # 库存只有 3 件的商品
RACE_WINDOW = 0.3         # 放大后的竞态窗口（秒）


@pytest.fixture
def wide_race_window():
    """把服务端的竞态窗口临时放大，保证缺陷稳定复现。"""
    old = config.SIMULATE_DB_LATENCY
    config.SIMULATE_DB_LATENCY = RACE_WINDOW
    yield
    config.SIMULATE_DB_LATENCY = old


def _prepare_buyers(api):
    """准备 N 个已登录、购物车里各有 1 件商品的用户。"""
    buyers = []
    for i in range(CONCURRENCY):
        username = "race_%02d" % i
        api.register(username, "123456")

        c = ApiClient(BASE_URL)
        c.login(username)
        c.add_to_cart(PRODUCT_ID, 1)
        buyers.append((c, [x["id"] for x in c.cart_items()]))
    return buyers


def _run_concurrent_order(buyers):
    """所有线程在同一起跑线出发，各下一单。返回每条请求的错误码。"""
    results = []
    lock = threading.Lock()
    gate = threading.Barrier(len(buyers))

    def place_order(client, cart_ids):
        gate.wait()                       # 闸门：等所有线程就位再一起冲
        status, body = client.create_order(cart_ids)
        with lock:
            results.append(body.get("code"))

    threads = [
        threading.Thread(target=place_order, args=(c, ids)) for c, ids in buyers
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


@pytest.mark.xfail(reason="BUG-003：库存校验与扣减非原子，并发下超卖", strict=True)
def test_concurrent_order_should_not_oversell(api, db, wide_race_window):
    """库存 3 件、20 个并发下单，既不该超卖，成交数也不该超过库存"""
    stock_before = stock_of(db, PRODUCT_ID)
    assert stock_before == 3, "前置条件：商品 %d 初始库存应为 3" % PRODUCT_ID

    buyers = _prepare_buyers(api)
    assert len(buyers) == CONCURRENCY

    results = _run_concurrent_order(buyers)

    succeeded = results.count("OK")
    rejected = results.count("INSUFFICIENT_STOCK")
    other = [c for c in results if c not in ("OK", "INSUFFICIENT_STOCK")]
    final_stock = stock_of(db, PRODUCT_ID)

    assert not other, "出现了预期外的返回码：%s" % other

    assert succeeded <= 3, (
        "超卖：库存只有 3 件，却有 %d 笔订单成交（被拒 %d 笔），最终库存 %d"
        % (succeeded, rejected, final_stock)
    )
    assert final_stock >= 0, (
        "库存被扣成负数：%d（成交 %d 笔）" % (final_stock, succeeded)
    )
