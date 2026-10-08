# -*- coding: utf-8 -*-
"""易淘商城 · 演示数据生成

给项目灌一批「看起来像真在运营」的数据，方便手工测试和面试演示：

    商品    6  →  66 条（4 个分类）
    用户    3  →  33 条
    订单    0  →  220 条（已支付 / 待支付 / 已取消 都有）
    领券   6 张 → 66 张
    购物车 若干条

用法：
    python demo_data.py          # 灌演示数据（会先重置为初始状态）
    python demo_data.py clear    # 清掉演示数据，回到 sql/seed.sql 的干净基线

设计要点（也是测试时可以直接拿来验证的不变量）：
    1. 每一次库存变动都同步写 stock_logs，
       所以「商品库存 == 该商品流水合计」永远成立；
    2. 订单金额满足 amount == total_amount - discount_amount；
    3. 取消的订单必须把库存加回去，并且留下 ORDER_CANCEL 流水；
    4. 随机种子固定，每次生成的数据完全一致，方便反复对照。
"""
import datetime
import decimal
import random
import sys

import db
import init_db

random.seed(20261009)

CENT = decimal.Decimal("0.01")

# ----------------------------------------------------------------------
# 新增商品：(名称, 分类, 单价, 库存, 描述)
# ----------------------------------------------------------------------
NEW_PRODUCTS = [
    # ---- 数码 ----
    ("入耳式有线耳机", "数码", 49.00, 200, "3.5mm 接口，线控带麦"),
    ("蓝牙音箱 桌面版", "数码", 159.00, 60, "双单元立体声，续航 12 小时"),
    ("无线静音鼠标", "数码", 89.00, 120, "2.4G 无线，静音微动"),
    ("机械键盘 104键", "数码", 399.00, 30, "茶轴，带数字小键盘"),
    ("移动硬盘 1TB", "数码", 349.00, 40, "USB3.0 高速传输"),
    ("U盘 64G", "数码", 39.90, 300, "金属外壳，防水防摔"),
    ("USB 拓展坞 7合1", "数码", 129.00, 80, "HDMI + 千兆网口 + 读卡器"),
    ("电竞鼠标垫 900×400", "数码", 29.90, 150, "加厚锁边，顺滑面"),
    ("铝合金电脑支架", "数码", 79.00, 90, "六档调节，散热镂空"),
    ("高清网络摄像头", "数码", 199.00, 45, "1080P，带降噪麦克风"),
    ("双频无线路由器", "数码", 239.00, 35, "WiFi6，四天线"),
    ("蓝牙自拍杆三脚架", "数码", 69.00, 70, "可拆卸遥控器"),
    ("智能运动手环", "数码", 249.00, 55, "心率血氧监测，14 天续航"),
    ("氮化镓快充充电器 65W", "数码", 119.00, 100, "双口输出，支持笔记本"),
    ("便携迷你投影仪", "数码", 1299.00, 12, "1080P 物理分辨率，自动对焦"),
    # ---- 服饰 ----
    ("牛津纺长袖衬衫", "服饰", 139.00, 60, "免烫抗皱，商务通勤"),
    ("直筒牛仔裤", "服饰", 219.00, 45, "弹力面料，四季可穿"),
    ("连帽加绒卫衣", "服饰", 179.00, 70, "加厚抓绒，宽松版型"),
    ("轻薄羽绒服", "服饰", 499.00, 25, "90 白鸭绒，可收纳"),
    ("针织开衫外套", "服饰", 159.00, 55, "柔顺亲肤，不易起球"),
    ("休闲西装外套", "服饰", 399.00, 20, "微弹面料，修身剪裁"),
    ("百褶半身裙", "服饰", 169.00, 40, "垂坠感好，配腰带"),
    ("轻量运动跑鞋", "服饰", 329.00, 50, "回弹中底，透气网面"),
    ("纯棉棒球帽", "服饰", 69.00, 120, "可调节后扣，遮阳"),
    ("羊绒混纺围巾", "服饰", 128.00, 80, "加厚保暖，多色可选"),
    ("纯棉中筒袜 5双装", "服饰", 39.90, 200, "抗菌防臭，四季款"),
    ("头层牛皮腰带", "服饰", 158.00, 60, "自动扣，可裁剪"),
    ("双肩通勤背包", "服饰", 259.00, 35, "15.6 寸电脑仓，防泼水"),
    ("全棉家居睡衣套装", "服饰", 149.00, 65, "长袖长裤，亲肤透气"),
    ("防晒冰袖 2双装", "服饰", 19.90, 300, "UPF50+，凉感面料"),
    # ---- 食品 ----
    ("现磨挂耳咖啡 20包", "食品", 88.00, 90, "中深烘焙，阿拉比卡豆"),
    ("特级明前龙井", "食品", 168.00, 40, "一芽一叶，罐装 100g"),
    ("72% 黑巧克力", "食品", 45.90, 100, "可可脂含量高，微苦回甘"),
    ("手工曲奇礼盒", "食品", 68.00, 70, "黄油现烤，四种口味"),
    ("全脂纯牛奶 250ml×12", "食品", 59.90, 120, "3.6g 乳蛋白，常温保存"),
    ("洋槐花蜂蜜 500g", "食品", 78.00, 60, "波美度 42，未添加"),
    ("五常稻花香大米 5kg", "食品", 79.90, 150, "当季新米，真空装"),
    ("特级初榨橄榄油 1L", "食品", 128.00, 50, "冷压榨，酸度 0.3"),
    ("日式豚骨拉面 5包装", "食品", 39.90, 200, "含叉烧与笋干料包"),
    ("原切薯片 3桶装", "食品", 45.00, 180, "非油炸，海盐味"),
    ("新疆和田枣 500g", "食品", 55.00, 90, "皮薄肉厚，自然晾晒"),
    ("手撕风干牛肉干 200g", "食品", 66.00, 80, "原切后腿肉，五香味"),
    ("零添加生抽酱油 500ml", "食品", 29.90, 160, "古法酿造，180 天"),
    ("即食纯燕麦片 1kg", "食品", 49.90, 110, "无蔗糖，冲调方便"),
    ("海盐苏打饼干 500g", "食品", 32.00, 140, "低糖，独立小包"),
    # ---- 家居 ----
    ("慢回弹记忆棉枕", "家居", 159.00, 60, "护颈曲线，可拆洗"),
    ("全棉四件套 1.8m", "家居", 399.00, 30, "60 支长绒棉，亲肤"),
    ("折叠收纳箱 66L", "家居", 69.00, 100, "牛津布，加厚承重"),
    ("国AA级护眼台灯", "家居", 189.00, 45, "无频闪，五档调光"),
    ("感应式垃圾桶 12L", "家居", 129.00, 50, "红外感应，静音开盖"),
    ("无痕防滑衣架 20个", "家居", 39.90, 180, "加厚不伤衣，可叠挂"),
    ("情侣棉拖鞋", "家居", 49.00, 90, "防滑底，可机洗"),
    ("珊瑚绒浴巾 加大款", "家居", 59.00, 100, "吸水快干，不掉毛"),
    ("316 不锈钢保温杯 500ml", "家居", 89.00, 120, "24 小时保温，车载款"),
    ("麦饭石不粘炒锅 32cm", "家居", 199.00, 40, "少油烟，可用铁铲"),
    ("陶瓷餐具 18 件套", "家居", 158.00, 35, "釉下彩，可微波炉"),
    ("客厅短绒地毯 1.6m", "家居", 269.00, 25, "可机洗，防滑底"),
    ("全遮光窗帘 1.5m×2", "家居", 179.00, 40, "隔热降噪，含挂钩"),
    ("免钉无痕挂钩 10个", "家居", 25.90, 250, "承重 5kg，不伤墙"),
    ("折叠落地晾衣架", "家居", 109.00, 60, "加粗钢管，承重 30kg"),
]

# 演示用户会拿到的两张券：券#1 无门槛减 10，券#2 满 100 减 20
BONUS_COUPON_IDS = (1, 2)
COUPON_CUT = {1: decimal.Decimal("10.00"), 2: decimal.Decimal("20.00")}
COUPON_MIN = {1: decimal.Decimal("0.00"), 2: decimal.Decimal("100.00")}

ORDER_COUNT = 220


def _ts(days_ago, with_time=True):
    """生成一个过去时间的字符串。"""
    base = datetime.datetime.now() - datetime.timedelta(days=days_ago)
    if with_time:
        base = base.replace(
            hour=random.randint(8, 22),
            minute=random.randint(0, 59),
            second=random.randint(0, 59),
        )
    return base.strftime("%Y-%m-%d %H:%M:%S")


def _count(table):
    return db.fetch_one("SELECT COUNT(*) AS n FROM " + table)["n"]


# ======================================================================
#  生成
# ======================================================================
def build():
    init_db.reset_data()
    print("  [1/6] 已重置为初始数据（sql/seed.sql）")

    # ---- 商品 ----
    for name, cat, price, stock, desc in NEW_PRODUCTS:
        pid = db.execute(
            "INSERT INTO products (name, category, price, stock, status, description) "
            "VALUES (%s, %s, %s, %s, 'ON_SALE', %s)",
            (name, cat, price, stock, desc),
        )
        db.execute(
            "INSERT INTO stock_logs (product_id, change_qty, reason) "
            "VALUES (%s, %s, 'INIT')",
            (pid, stock),
        )
    print("  [2/6] 商品：%d 条" % _count("products"))

    # ---- 用户 ----
    uids = []
    for i in range(1, 31):
        uid = db.execute(
            "INSERT INTO users (username, password, phone) VALUES (%s, %s, %s)",
            ("user_%02d" % i, "123456", "139%08d" % (10000000 + i)),
        )
        uids.append(uid)
    print("  [3/6] 用户：%d 条（user_01 ~ user_30 密码均为 123456）" % _count("users"))

    # ---- 给演示用户发券 ----
    avail = {}
    for uid in uids:
        own = {}
        for cid in BONUS_COUPON_IDS:
            ucid = db.execute(
                "INSERT INTO user_coupons (user_id, coupon_id, status) "
                "VALUES (%s, %s, 'UNUSED')",
                (uid, cid),
            )
            own[cid] = ucid
        avail[uid] = own
    db.execute(
        "UPDATE coupons SET claimed_count = claimed_count + %s WHERE id IN (1, 2)",
        (len(uids),),
    )
    print("  [4/6] 优惠券：用户持券 %d 张" % _count("user_coupons"))

    # ---- 订单 ----
    products = db.fetch_all(
        "SELECT id, name, price, stock FROM products "
        "WHERE status = 'ON_SALE' ORDER BY id"
    )
    stock = {p["id"]: p["stock"] for p in products}

    made = 0
    for n in range(ORDER_COUNT):
        uid = random.choice(uids)
        picks = random.sample(products, random.randint(1, 3))

        lines = []
        for p in picks:
            room = min(5, stock[p["id"]])
            if room <= 0:
                continue
            lines.append((p, random.randint(1, room)))
        if not lines:
            continue

        total = sum((decimal.Decimal(str(p["price"])) * q for p, q in lines),
                    decimal.Decimal("0.00"))
        total = total.quantize(CENT)

        # 三成订单用券：够门槛就优先用满减券，否则用无门槛券
        real_ucid = None
        discount = decimal.Decimal("0.00")
        if avail.get(uid) and random.random() < 0.30:
            pick = None
            for cand in (2, 1):
                if cand in avail[uid] and total >= COUPON_MIN[cand]:
                    pick = cand
                    break
            if pick:
                real_ucid = avail[uid].pop(pick)
                discount = COUPON_CUT[pick]
        ucid = real_ucid

        payable = (total - discount).quantize(CENT)
        created = _ts(random.randint(0, 45))

        r = random.random()
        if r < 0.60:
            status, pay_type = "PAID", random.choice(["ALIPAY", "WECHAT"])
            paid_at = _ts(random.randint(0, 45))
        elif r < 0.85:
            status, pay_type, paid_at = "PENDING", None, None
        else:
            status, pay_type, paid_at = "CANCELLED", None, None

        oid = db.execute(
            "INSERT INTO orders (user_id, amount, total_amount, discount_amount, "
            "                    user_coupon_id, status, pay_type, created_at, paid_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (uid, payable, total, discount, real_ucid, status, pay_type, created, paid_at),
        )

        for p, q in lines:
            db.execute(
                "INSERT INTO order_items "
                "(order_id, product_id, product_name, price, quantity) "
                "VALUES (%s, %s, %s, %s, %s)",
                (oid, p["id"], p["name"], p["price"], q),
            )
            db.execute("UPDATE products SET stock = stock - %s WHERE id = %s", (q, p["id"]))
            db.execute(
                "INSERT INTO stock_logs (product_id, change_qty, reason, order_id) "
                "VALUES (%s, %s, 'ORDER_CREATE', %s)",
                (p["id"], -q, oid),
            )
            stock[p["id"]] -= q

        if status == "CANCELLED":
            for p, q in lines:
                db.execute("UPDATE products SET stock = stock + %s WHERE id = %s", (q, p["id"]))
                db.execute(
                    "INSERT INTO stock_logs (product_id, change_qty, reason, order_id) "
                    "VALUES (%s, %s, 'ORDER_CANCEL', %s)",
                    (p["id"], q, oid),
                )
                stock[p["id"]] += q
        elif real_ucid:
            db.execute(
                "UPDATE user_coupons SET status = 'USED', order_id = %s, used_at = %s "
                "WHERE id = %s",
                (oid, created, real_ucid),
            )

        made += 1

    print("  [5/6] 订单：%d 条（附明细与库存流水）" % made)

    # ---- 购物车 ----
    cart_users = random.sample(uids, 12)
    for uid in cart_users:
        for p in random.sample(products, random.randint(1, 3)):
            db.execute(
                "INSERT INTO carts (user_id, product_id, quantity) VALUES (%s, %s, %s)",
                (uid, p["id"], random.randint(1, 3)),
            )
    print("  [6/6] 购物车：%d 行" % _count("carts"))
    print("")
    print("  完成。当前数据量：")
    for t in ("users", "products", "orders", "order_items",
              "carts", "coupons", "user_coupons", "stock_logs"):
        print("    %-14s %s" % (t, _count(t)))


def clear():
    init_db.reset_data()
    print("  已清掉演示数据，恢复到 sql/seed.sql 的干净基线。")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "clear":
        clear()
    else:
        build()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print("")
        print("  [错误] 生成演示数据失败：%s" % exc)
        sys.exit(1)
