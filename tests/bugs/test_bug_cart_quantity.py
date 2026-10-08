# -*- coding: utf-8 -*-
"""BUG-005 · 加入购物车不校验数量

缺陷类型：输入校验缺失
严重级别：中
根因：add_to_cart() 只校验商品是否存在、是否在售，
      对 quantity 不做任何校验 —— 0、负数、超过库存的数量全部放行。

影响：
    · 可以加 999 件到购物车（库存只有 3 件），造成误导
    · 可以加负数，配合下单会产生**负金额订单**
    · 数量校验被推迟到下单环节，属于「校验位置不当」

正确的做法是在 add_to_cart 里就做范围校验，
并在下单前再次确认（双保险）。
"""
import pytest


@pytest.mark.xfail(reason="BUG-005：add_to_cart 不校验 quantity 取值范围", strict=True)
def test_add_zero_quantity(user_a):
    """加入 0 件应当被拒绝"""
    status, body = user_a.add_to_cart(1, 0)
    assert status == 400, "加入 0 件商品应被拒绝，实际返回 %s" % status


@pytest.mark.xfail(reason="BUG-005：add_to_cart 不校验 quantity 取值范围", strict=True)
def test_add_negative_quantity(user_a):
    """加入负数件应当被拒绝"""
    status, body = user_a.add_to_cart(1, -5)
    assert status == 400, "加入负数件商品应被拒绝，实际返回 %s" % status


@pytest.mark.xfail(reason="BUG-005：add_to_cart 不校验 quantity 取值范围", strict=True)
def test_add_quantity_over_stock(user_a):
    """加入超过库存的数量应当被拒绝（商品 3 库存只有 3）"""
    status, body = user_a.add_to_cart(3, 999)
    assert status == 400, (
        "库存只有 3 件，却允许加入 999 件，返回 %s" % status
    )


@pytest.mark.xfail(reason="BUG-005 的连带影响：负数数量产生负金额订单", strict=True)
def test_negative_quantity_cannot_create_negative_order(user_a):
    """负数加购 + 下单，不应产生负金额订单"""
    user_a.add_to_cart(1, -3)
    cid = user_a.cart_items()[0]["id"]
    status, body = user_a.create_order([cid])

    if status == 200:
        assert body["data"]["amount"] > 0, (
            "产生了负金额订单：amount = %s" % body["data"]["amount"]
        )
    else:
        assert status == 400
