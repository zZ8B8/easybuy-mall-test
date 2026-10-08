# -*- coding: utf-8 -*-
"""BUG-007 · 折扣券把「折扣率」当成了「减免比例」

缺陷类型：需求语义理解错误 / 金额计算错误
严重级别：高（直接漏钱）
根因：需求规定 DISCOUNT 券的 value 是**折扣率**：
          value = 0.88  →  「88 折」→ 用户实付 88%，平台让利 12%
      但 _calc_discount() 里写成了：
          discount = total × value
      把折扣率当成了「减免掉的比例」。

算一遍（订单小计 199.00，券#3 = 全场 88 折）：

    需求要求          discount = 199 × (1 - 0.88) = 23.88   实付 175.12
    实际实现          discount = 199 × 0.88      = 175.12  实付  23.88

平台每卖一单就少收 12% 的钱，而且**金额恒等式还是平的**
（实付 = 小计 - 优惠，账面对得上），所以只靠「对账」发现不了，
必须拿需求文档里的算例去逐笔核对金额。

修复思路：DISCOUNT 分支改成
        discount = total × (1 - value)
"""
import pytest


def order_with_coupon(client, product_id, quantity=1, user_coupon_id=None):
    client.add_to_cart(product_id, quantity)
    cart_ids = [client.cart_items()[0]["id"]]
    payload = {"cartIds": cart_ids}
    if user_coupon_id:
        payload["userCouponId"] = user_coupon_id
    return client.post("/api/orders", payload)


@pytest.mark.xfail(reason="BUG-007：折扣率被当成减免比例计算", strict=True)
def test_discount_coupon_amount(user_a):
    """业务规则：全场 88 折买 199 元，应减 23.88，实付 175.12"""
    status, body = order_with_coupon(user_a, 1, 1, user_coupon_id=3)
    assert status == 200
    o = body["data"]
    assert o["discount_amount"] == pytest.approx(23.88, abs=0.01), (
        "88 折券应减 23.88 元（199 × 12%%），实际减了 %s 元" % o["discount_amount"]
    )
    assert o["amount"] == pytest.approx(175.12, abs=0.01), (
        "实付应为 175.12 元，实际 %s 元" % o["amount"]
    )


@pytest.mark.xfail(reason="BUG-007：折扣券抵扣额大得离谱", strict=True)
def test_discount_never_exceeds_expected(user_a):
    """BUG-007 的危害：折扣券抵扣额不可能超过订单金额的一半"""
    _, body = order_with_coupon(user_a, 1, 1, user_coupon_id=3)
    o = body["data"]
    assert o["discount_amount"] <= o["total_amount"] * 0.5, (
        "88 折券抵扣了 %s 元，占订单金额的 %.1f%%"
        % (o["discount_amount"], o["discount_amount"] / o["total_amount"] * 100)
    )


def test_amount_identity_still_holds(user_a):
    """对照用例：金额恒等式仍然成立 —— 所以光对账是发现不了 BUG-007 的

    这条用例会通过：实付 == 小计 - 优惠 始终成立。
    它存在的意义是提醒你：**对账平不平，和金额算得对不对，是两码事。**
    """
    _, body = order_with_coupon(user_a, 1, 1, user_coupon_id=3)
    o = body["data"]
    assert o["amount"] == pytest.approx(o["total_amount"] - o["discount_amount"])
