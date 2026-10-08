# -*- coding: utf-8 -*-
"""BUG-002 · 重复取消订单导致库存虚增

缺陷类型：幂等性缺陷
严重级别：高
根因：cancel_order() 没有判断订单当前状态，每次都执行
      「改状态 + 回滚库存」。取消两次，库存就还两次。

影响：库存无中生有。50 件商品取消两次变 52 件，
      账实不符，超卖风险随之而来。
"""
import pytest

from tests.conftest import stock_of


@pytest.mark.xfail(reason="BUG-002：cancel_order 缺少幂等校验", strict=True)
def test_double_cancel_should_not_duplicate_stock(user_a, db):
    """同一订单取消两次，库存应当只回滚一次"""
    before = stock_of(db, 4)

    user_a.add_to_cart(4, 2)
    cid = user_a.cart_items()[0]["id"]
    order_id = user_a.create_order([cid])[1]["data"]["id"]
    after_order = stock_of(db, 4)
    assert after_order == before - 2

    user_a.cancel(order_id)
    after_first = stock_of(db, 4)
    user_a.cancel(order_id)
    after_second = stock_of(db, 4)

    assert after_second == after_first, (
        "重复取消导致库存被再次回滚：第1次取消后 %s，第2次取消后 %s（初始 %s）"
        % (after_first, after_second, before)
    )


@pytest.mark.xfail(reason="BUG-002：cancel_order 缺少幂等校验", strict=True)
def test_double_cancel_writes_duplicate_log(user_a, db):
    """同一订单重复取消，只应写一条回滚流水"""
    user_a.add_to_cart(4, 2)
    cid = user_a.cart_items()[0]["id"]
    order_id = user_a.create_order([cid])[1]["data"]["id"]

    user_a.cancel(order_id)
    user_a.cancel(order_id)

    with db.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM stock_logs "
            "WHERE order_id = %s AND reason = 'ORDER_CANCEL'",
            (order_id,),
        )
        n = cur.fetchone()[0]

    assert n == 1, (
        "订单 %s 被取消了两次，却写了 %d 条回滚流水 —— 库存被重复回滚" % (order_id, n)
    )
