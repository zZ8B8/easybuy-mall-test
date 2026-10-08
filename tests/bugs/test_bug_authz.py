# -*- coding: utf-8 -*-
"""BUG-004 · 水平越权（IDOR）：可查看并取消他人的订单

缺陷类型：访问控制 / 越权
严重级别：严重
根因：get_order() 和 cancel_order() 只按订单号查询，
      没有校验「这笔订单属不属于当前登录用户」。

影响：
    · 任何登录用户只要把订单号从 1 递增遍历，就能拿到全站订单
      （谁买了什么、花了多少钱、收货信息）
    · 还能直接取消别人的订单 —— 这是破坏性操作

这是 OWASP API Security Top 10 里的 API1: BOLA（Broken Object Level
Authorization），真实线上环境里非常常见，测试面试也特别爱问。
"""
import pytest


@pytest.mark.xfail(reason="BUG-004：订单详情未校验归属，存在越权", strict=True)
def test_cannot_view_others_order(user_a, user_b):
    """user_a 不应能查看 user_b 的订单"""
    user_b.add_to_cart(5, 1)
    cid = user_b.cart_items()[0]["id"]
    b_order_id = user_b.create_order([cid])[1]["data"]["id"]

    status, body = user_a.order(b_order_id)
    assert status in (403, 404), (
        "user_a(自己没下单) 却查到了 user_b 的订单 %s：HTTP %s，"
        "内容=%s" % (b_order_id, status, body.get("data"))
    )


@pytest.mark.xfail(reason="BUG-004：取消订单未校验归属，可越权取消", strict=True)
def test_cannot_cancel_others_order(user_a, user_b, db):
    """user_a 不应能取消 user_b 的订单"""
    user_b.add_to_cart(5, 1)
    cid = user_b.cart_items()[0]["id"]
    b_order_id = user_b.create_order([cid])[1]["data"]["id"]

    status, body = user_a.cancel(b_order_id)

    with db.cursor() as cur:
        cur.execute("SELECT status FROM orders WHERE id = %s", (b_order_id,))
        real_status = cur.fetchone()[0]

    assert real_status == "PENDING", (
        "user_a 越权取消了 user_b 的订单 %s，数据库里状态已变成 %s"
        % (b_order_id, real_status)
    )


@pytest.mark.xfail(reason="BUG-004：订单号可枚举，能遍历出他人订单", strict=True)
def test_cannot_enumerate_orders(user_a, user_b):
    """订单号连续递增，不应能被遍历出别人的订单"""
    ids = []
    for i in range(3):
        user_b.add_to_cart(5, 1)
        cid = user_b.cart_items()[0]["id"]
        ids.append(user_b.create_order([cid])[1]["data"]["id"])

    leaked = []
    for oid in ids:
        status, body = user_a.order(oid)
        if status == 200 and body.get("code") == "OK":
            leaked.append((oid, body["data"]["amount"]))

    assert not leaked, "user_a 遍历（并未购买）看到了 user_b 的 %d 笔订单：%s" % (
        len(leaked), leaked
    )
