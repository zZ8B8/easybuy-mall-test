# -*- coding: utf-8 -*-
"""BUG-008 · 领券不校验每人限领张数

缺陷类型：业务规则校验缺失
严重级别：中
根因：claim_coupon() 只校验了「券存在」「状态是 ACTIVE」「未过期」，
      **没有校验 per_user_limit（每人限领）**，
      也**没有校验 total_count（发放总量）**。

影响：
    · coupons.per_user_limit 字段形同虚设 —— 同一个账号可以对着同一张券点到手软
    · coupons.claimed_count 会一路涨上去，与「发放总量」脱钩，券超发
    · 下游风控 / 营销统计全部失真

反例：黑产账号批量领券，再把券挂到二手平台倒卖。

修复思路：领券前先查两张表
        SELECT COUNT(*) FROM user_coupons WHERE user_id=? AND coupon_id=?
        SELECT claimed_count, total_count FROM coupons WHERE id=?
      任一超限就返回 400。
"""
import pytest


@pytest.mark.xfail(reason="BUG-008：领券未校验 per_user_limit", strict=True)
def test_cannot_exceed_per_user_limit(user_a):
    """业务规则：券#3（满300减50）每人限领 2 张，领第 3 张应被拒绝"""
    assert user_a.post("/api/coupons/3/claim", {})[0] == 200
    assert user_a.post("/api/coupons/3/claim", {})[0] == 200

    status, body = user_a.post("/api/coupons/3/claim", {})
    assert status == 400, (
        "per_user_limit=2，第 3 张应当被拒绝，实际返回 %s" % status
    )


@pytest.mark.xfail(reason="BUG-008：限领 1 张的券被反复领取", strict=True)
def test_single_limit_coupon_claimed_once(user_a):
    """业务规则：券#1（新人券）每人限领 1 张，重复领取应被拒绝"""
    codes = [user_a.post("/api/coupons/1/claim", {})[0] for _ in range(4)]
    assert codes.count(200) <= 1, (
        "per_user_limit=1，实际成功领取 %d 次" % codes.count(200)
    )


@pytest.mark.xfail(reason="BUG-008：限领失效导致同一批账号把券刷走", strict=True)
def test_claim_count_respects_per_user_limit(user_a, user_b, db):
    """数据一致性：券#4（全场88折）每人限领 1 张

    user_a 初始已有 1 张。让两个账号各领 5 次，
    claimed_count 最多只应增加 2（A 超限、B 超限都被拦）。
    """
    with db.cursor() as cur:
        cur.execute("SELECT claimed_count FROM coupons WHERE id=4")
        before = cur.fetchone()[0]

    for _ in range(5):
        user_a.post("/api/coupons/4/claim", {})
        user_b.post("/api/coupons/4/claim", {})

    with db.cursor() as cur:
        cur.execute("SELECT claimed_count FROM coupons WHERE id=4")
        after = cur.fetchone()[0]

    assert after - before <= 2, (
        "每人限领 1 张，两个账号合计最多领 2 张，实际领走了 %d 张" % (after - before)
    )
