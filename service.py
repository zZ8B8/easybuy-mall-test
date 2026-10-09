# -*- coding: utf-8 -*-
"""易淘商城 · 业务逻辑层

所有业务规则都在这个文件里。接口层（app.py）只负责解析请求、调用这里、返回 JSON。

⚠️ 本项目是「测试靶场」：下面标注了 7 处**刻意保留的缺陷**。
   代码里用「⚠️ 缺陷 BUG-xxx」的注释标了出来，方便你对着注释读代码；
   但真正做测试时，请先自己找、自己写用例复现，最后再翻注释对照。
   缺陷清单见 docs/05-缺陷报告.md。
"""
import datetime
import decimal
import secrets

import db

# ------------------------------------------------------------------
# 业务常量
# ------------------------------------------------------------------
ORDER_PENDING = "PENDING"
ORDER_PAID = "PAID"
ORDER_CANCELLED = "CANCELLED"

PRODUCT_ON_SALE = "ON_SALE"

MAX_ORDER_QUANTITY = 99

# 券型
COUPON_THRESHOLD = "THRESHOLD"   # 满减
COUPON_DISCOUNT = "DISCOUNT"     # 折扣
COUPON_FREE = "FREE"             # 无门槛

# 用户券状态
UC_UNUSED = "UNUSED"
UC_USED = "USED"
UC_EXPIRED = "EXPIRED"

COUPON_TYPE_NAME = {
    COUPON_THRESHOLD: "满减券",
    COUPON_DISCOUNT: "折扣券",
    COUPON_FREE: "无门槛券",
}

_CENT = decimal.Decimal("0.01")


class ApiError(Exception):
    """业务异常：接口层捕获后转成统一的 JSON 错误响应。"""

    def __init__(self, code, message, http_status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _money(value):
    """数据库取出来的 DECIMAL 转成 float，方便转 JSON。"""
    if value is None:
        return None
    if isinstance(value, decimal.Decimal):
        return float(value)
    return float(value)


# ==================================================================
#  用户
# ==================================================================
def register(username, password, phone=None):
    if not username or not str(username).strip():
        raise ApiError("INVALID_PARAM", "用户名不能为空", 400)
    if not password:
        raise ApiError("INVALID_PARAM", "密码不能为空", 400)

    username = str(username).strip()
    exists = db.fetch_one("SELECT id FROM users WHERE username = %s", (username,))
    if exists:
        raise ApiError("USERNAME_EXISTS", "用户名已被占用", 400)

    uid = db.execute(
        "INSERT INTO users (username, password, phone) VALUES (%s, %s, %s)",
        (username, password, phone),
    )
    return {"id": uid, "username": username}


def login(username, password):
    row = db.fetch_one(
        "SELECT id, username, password FROM users WHERE username = %s", (username,)
    )
    if not row or row["password"] != password:
        # 用户名不存在和密码错误返回同一个错误码，避免暴露账号是否存在
        raise ApiError("LOGIN_FAILED", "用户名或密码错误", 401)

    token = secrets.token_hex(16)
    db.execute(
        "INSERT INTO sessions (token, user_id) VALUES (%s, %s)", (token, row["id"])
    )
    return token


def current_user(token):
    """鉴权：把 token 换成用户。任何需要登录的接口都要先过这一步。"""
    if not token:
        raise ApiError("UNAUTHORIZED", "未登录或登录已失效", 401)
    row = db.fetch_one(
        "SELECT u.id, u.username FROM sessions s "
        "JOIN users u ON u.id = s.user_id WHERE s.token = %s",
        (token,),
    )
    if not row:
        raise ApiError("UNAUTHORIZED", "未登录或登录已失效", 401)
    return row


# ==================================================================
#  商品
# ==================================================================
def list_products(page=1, size=10, category=None):
    where, args = "", []
    if category:
        where = " WHERE category = %s"
        args.append(category)

    total = db.fetch_one("SELECT COUNT(*) AS n FROM products" + where, args)["n"]
    offset = (page - 1) * size
    rows = db.fetch_all(
        "SELECT id, name, category, price, stock, status, description "
        "FROM products" + where + " ORDER BY id LIMIT %s OFFSET %s",
        args + [size, offset],
    )
    for r in rows:
        r["price"] = _money(r["price"])
        # 只有在售商品才对外暴露可购买；下架商品库存归零显示
        if r["status"] != PRODUCT_ON_SALE:
            r["stock"] = 0
    return {"total": total, "page": page, "size": size, "items": rows}


def get_product(product_id):
    row = db.fetch_one(
        "SELECT id, name, category, price, stock, status, description "
        "FROM products WHERE id = %s",
        (product_id,),
    )
    if not row:
        raise ApiError("PRODUCT_NOT_FOUND", "商品不存在", 404)
    row["price"] = _money(row["price"])
    if row["status"] != PRODUCT_ON_SALE:
        row["stock"] = 0
    return row


# ==================================================================
#  购物车
# ==================================================================
def add_to_cart(user_id, product_id, quantity):
    """加入购物车。

    ⚠️ 缺陷 BUG-005（已知，报告里也有记录）：
      这里不校验 quantity —— 传 0、负数、超过库存的数量都能加进购物车。
      库存校验被推迟到了「下单」那一步。
      从接口测试角度看，这是典型的「缺少参数有效性校验」。
    """
    if quantity is None:
        raise ApiError("INVALID_PARAM", "缺少 quantity", 400)

    product = db.fetch_one(
        "SELECT id, status FROM products WHERE id = %s", (product_id,)
    )
    if not product:
        raise ApiError("PRODUCT_NOT_FOUND", "商品不存在", 404)
    if product["status"] != PRODUCT_ON_SALE:
        raise ApiError("PRODUCT_OFF_SALE", "商品已下架", 400)

    db.execute(
        "INSERT INTO carts (user_id, product_id, quantity) VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE quantity = quantity + VALUES(quantity)",
        (user_id, product_id, quantity),
    )
    row = db.fetch_one(
        "SELECT id, product_id, quantity FROM carts "
        "WHERE user_id = %s AND product_id = %s",
        (user_id, product_id),
    )
    return row


def list_cart(user_id):
    rows = db.fetch_all(
        "SELECT c.id, c.product_id, p.name AS product_name, p.price, "
        "       c.quantity, p.stock "
        "FROM carts c JOIN products p ON p.id = c.product_id "
        "WHERE c.user_id = %s ORDER BY c.id",
        (user_id,),
    )
    for r in rows:
        r["price"] = _money(r["price"])
    return rows


def update_cart_quantity(user_id, cart_id, quantity):
    row = db.fetch_one(
        "SELECT id FROM carts WHERE id = %s AND user_id = %s", (cart_id, user_id)
    )
    if not row:
        raise ApiError("CART_NOT_FOUND", "购物车记录不存在", 404)
    if quantity is None:
        raise ApiError("INVALID_PARAM", "缺少 quantity", 400)
    db.execute("UPDATE carts SET quantity = %s WHERE id = %s", (quantity, cart_id))
    return {"cartId": cart_id, "quantity": quantity}


def remove_cart_item(user_id, cart_id):
    row = db.fetch_one(
        "SELECT id FROM carts WHERE id = %s AND user_id = %s", (cart_id, user_id)
    )
    if not row:
        raise ApiError("CART_NOT_FOUND", "购物车记录不存在", 404)
    db.execute("DELETE FROM carts WHERE id = %s", (cart_id,))
    return {"removed": cart_id}


# ==================================================================
#  优惠券
# ==================================================================
def list_coupons():
    """领券中心：当前可领取的券（状态 ACTIVE 且未过期）。

    remain = -1 表示不限量，前端见到 -1 显示「不限量」。
    """
    rows = db.fetch_all(
        "SELECT id, code, name, type, threshold, value, total_count, claimed_count, "
        "       per_user_limit, valid_from, valid_to, status "
        "FROM coupons WHERE status = 'ACTIVE' AND valid_to > NOW() ORDER BY id"
    )
    for r in rows:
        r["threshold"] = _money(r["threshold"])
        r["value"] = _money(r["value"])
        r["typeName"] = COUPON_TYPE_NAME.get(r["type"], r["type"])
        r["remain"] = (
            -1 if not r["total_count"]
            else max(0, r["total_count"] - r["claimed_count"])
        )
    return rows


def claim_coupon(user_id, coupon_id):
    """领取优惠券。

    ⚠️ 缺陷 BUG-008（中 · 缺少业务校验）：
      这里只校验了「券存在、没停发、没过期」，
      **没有校验每人限领张数（per_user_limit）**，
      也**没有校验发放总量（total_count）**。
      于是一个账号可以对着同一张券点到手软，
      claimed_count 一直涨到超过 total_count —— 券「超发」了。
      复现方式：连续调用领券接口 3 次，3 次全部成功。
    """
    coupon = db.fetch_one(
        "SELECT id, name, status, total_count, claimed_count, per_user_limit "
        "FROM coupons WHERE id = %s AND valid_to > NOW()",
        (coupon_id,),
    )
    if not coupon:
        raise ApiError("COUPON_NOT_FOUND", "优惠券不存在或已过期", 404)
    if coupon["status"] != "ACTIVE":
        raise ApiError("COUPON_DISABLED", "该券已停止发放", 400)

    # 这里本该有：已领张数 >= per_user_limit 就报错；claimed_count >= total_count 就报错。

    uc_id = db.execute(
        "INSERT INTO user_coupons (user_id, coupon_id, status) VALUES (%s, %s, %s)",
        (user_id, coupon_id, UC_UNUSED),
    )
    db.execute(
        "UPDATE coupons SET claimed_count = claimed_count + 1 WHERE id = %s",
        (coupon_id,),
    )
    return {
        "userCouponId": uc_id,
        "couponId": coupon_id,
        "couponName": coupon["name"],
        "status": UC_UNUSED,
    }


def list_user_coupons(user_id, status=None):
    """我的券包。status 可选：UNUSED / USED / EXPIRED。"""
    sql = (
        "SELECT uc.id, uc.coupon_id, uc.status, uc.order_id, uc.claimed_at, uc.used_at, "
        "       c.code, c.name, c.type, c.threshold, c.value, c.valid_from, c.valid_to, "
        "       (c.valid_to < NOW()) AS expired "
        "FROM user_coupons uc JOIN coupons c ON c.id = uc.coupon_id "
        "WHERE uc.user_id = %s"
    )
    args = [user_id]
    if status:
        sql += " AND uc.status = %s"
        args.append(status)
    sql += " ORDER BY uc.id DESC"

    rows = db.fetch_all(sql, args)
    for r in rows:
        r["threshold"] = _money(r["threshold"])
        r["value"] = _money(r["value"])
        r["typeName"] = COUPON_TYPE_NAME.get(r["type"], r["type"])
        # 「过期」是时间到了，「已用」是被核销了 —— 两件事分开表达
        if r["status"] == UC_UNUSED and r["expired"]:
            r["status"] = UC_EXPIRED
        r["usable"] = r["status"] == UC_UNUSED
        r.pop("expired", None)
    return rows


def _load_user_coupon(user_id, user_coupon_id):
    """取一张用户券，并做归属与有效性校验。

    ⚠️ 缺陷 BUG-006（高 · 状态机）：
      这里检查了「券存不存在」「是不是本人的」「过没过期」，
      **唯独漏掉了「这张券是不是已经被用过了」**。
      下单成功后券会被标记成 USED，界面上显示「已使用」，
      但下单接口压根不看这个状态 —— 同一张券可以反复抵扣。
      「接口行为与界面展示不一致」，这是接口测试的经典猎物。
    """
    uc = db.fetch_one(
        "SELECT uc.id, uc.user_id, uc.status, uc.order_id, "
        "       c.id AS coupon_id, c.code, c.name, c.type, c.threshold, c.value, "
        "       c.valid_from, c.valid_to, (c.valid_to < NOW()) AS expired "
        "FROM user_coupons uc JOIN coupons c ON c.id = uc.coupon_id "
        "WHERE uc.id = %s",
        (user_coupon_id,),
    )
    if not uc:
        raise ApiError("COUPON_NOT_FOUND", "优惠券不存在", 404)
    if uc["user_id"] != user_id:
        # 别人的券一律当「不存在」，不暴露「这张券是别人的」
        raise ApiError("COUPON_NOT_FOUND", "优惠券不存在", 404)
    if uc["expired"]:
        raise ApiError("COUPON_EXPIRED", "优惠券已过期", 400)
    # 这里本该有：if uc["status"] == UC_USED: raise ApiError("COUPON_USED", ...)
    return uc


def _calc_discount(coupon, total):
    """按券型算出这张券能减多少钱，返回 Decimal。

    ✅ 已修复（原 BUG-007 · 高 · 金额计算）：
      DISCOUNT 券的 value 是**折扣率**：value=0.88 表示「88 折」，
      用户实付 88%、平台让利 12%，即 discount = total × (1 - value)。
      修复前误写成 discount = total × value（把折扣率当成减免比例），
      199 元订单会被减掉 175.12 元、实付只剩 23.88 元，单笔少收 151.24 元；
      且金额恒等式「实付 = 小计 − 优惠」依然成立，只做对账根本发现不了。
      回归用例：tests/bugs/test_bug_coupon_discount.py
    """
    total = decimal.Decimal(str(total))

    # 门槛统一在这里判：threshold 为 0（无门槛券）时自然跳过
    threshold = decimal.Decimal(str(coupon["threshold"] or 0))
    if threshold > 0 and total < threshold:
        raise ApiError(
            "COUPON_THRESHOLD_NOT_MET",
            "订单小计 %s 元未满 %s 元，不能使用该券" % (total, threshold),
            400,
        )

    if coupon["type"] == COUPON_DISCOUNT:
        # value 是折扣率（0.88 ＝ 88 折），用户实付 value 比例，平台让利 (1 - value)
        rate = decimal.Decimal(str(coupon["value"]))
        discount = (total * (decimal.Decimal("1") - rate)).quantize(_CENT)
    else:
        # THRESHOLD 满减 / FREE 无门槛：value 就是减免金额
        discount = decimal.Decimal(str(coupon["value"]))

    if discount > total:
        discount = total
    return discount


# ==================================================================
#  订单
# ==================================================================
def create_order(user_id, cart_ids, user_coupon_id=None):
    """下单：校验 -> 算优惠 -> 扣库存 -> 生成订单。

    ⚠️ 缺陷 BUG-003（严重 · 并发）：
      「读库存」和「扣库存」分成了两次独立的数据库操作，
      中间没有任何锁或原子保证。多线程同时下单时，
      每个线程都读到同一个「还有货」的快照，
      于是都能通过校验，最后库存被扣成负数 —— 超卖。
      复现方式见 tests/test_bug_stock_concurrency.py
    """
    if not cart_ids:
        raise ApiError("EMPTY_CART", "请先选择要购买的商品", 400)

    placeholders = ",".join(["%s"] * len(cart_ids))
    cart_rows = db.fetch_all(
        "SELECT c.id, c.product_id, c.quantity FROM carts c "
        "WHERE c.id IN (" + placeholders + ") AND c.user_id = %s",
        list(cart_ids) + [user_id],
    )
    if len(cart_rows) != len(cart_ids):
        raise ApiError("CART_NOT_FOUND", "购物车记录不存在", 404)

    # ---- 第一步：逐个读商品、校验、累加小计（非锁定的普通查询）----
    checked = []
    total_amount = decimal.Decimal("0.00")
    for c in cart_rows:
        product = db.fetch_one(
            "SELECT id, name, price, stock, status FROM products WHERE id = %s",
            (c["product_id"],),
        )
        if not product:
            raise ApiError("PRODUCT_NOT_FOUND", "商品不存在", 404)
        if product["status"] != PRODUCT_ON_SALE:
            raise ApiError("PRODUCT_OFF_SALE", "商品「%s」已下架" % product["name"], 400)
        if c["quantity"] > MAX_ORDER_QUANTITY:
            raise ApiError(
                "INVALID_PARAM",
                "单笔最多购买 %d 件" % MAX_ORDER_QUANTITY,
                400,
            )
        if product["stock"] < c["quantity"]:
            raise ApiError(
                "INSUFFICIENT_STOCK",
                "商品「%s」库存不足，当前仅剩 %d 件" % (product["name"], product["stock"]),
                400,
            )
        checked.append((product, c["quantity"]))
        total_amount += decimal.Decimal(str(product["price"])) * c["quantity"]

    # ---- 第二步：算优惠 ----
    # 刻意放在扣库存之前：券不能用就直接报错，不能出现「库存扣了、订单没生成」。
    discount = decimal.Decimal("0.00")
    if user_coupon_id:
        coupon = _load_user_coupon(user_id, user_coupon_id)
        discount = _calc_discount(coupon, total_amount)
    payable = total_amount - discount

    # ---- 第三步：扣减库存（与第一步之间没有事务保护，缺陷所在）----
    # 这两步之间隔着一次数据库往返与线程调度，正是这段间隙让并发竞态成立。
    # 靶场把这段延迟显式化，保证缺陷稳定复现；改成 0 可观察窗口消失后的表现。
    db.simulate_round_trip()

    for product, qty in checked:
        db.execute(
            "UPDATE products SET stock = stock - %s WHERE id = %s",
            (qty, product["id"]),
        )

    # ---- 第四步：落订单 ----
    order_id = db.execute(
        "INSERT INTO orders "
        "(user_id, amount, total_amount, discount_amount, user_coupon_id, status) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (user_id, payable, total_amount, discount, user_coupon_id, ORDER_PENDING),
    )
    for product, qty in checked:
        db.execute(
            "INSERT INTO order_items (order_id, product_id, product_name, price, quantity) "
            "VALUES (%s, %s, %s, %s, %s)",
            (order_id, product["id"], product["name"], product["price"], qty),
        )
        db.execute(
            "INSERT INTO stock_logs (product_id, change_qty, reason, order_id) "
            "VALUES (%s, %s, 'ORDER_CREATE', %s)",
            (product["id"], -qty, order_id),
        )

    # ---- 第五步：核销优惠券 ----
    if user_coupon_id:
        db.execute(
            "UPDATE user_coupons SET status = %s, order_id = %s, used_at = NOW() "
            "WHERE id = %s",
            (UC_USED, order_id, user_coupon_id),
        )

    # ---- 第六步：清掉已下单的购物车行 ----
    for c in cart_rows:
        db.execute("DELETE FROM carts WHERE id = %s", (c["id"],))

    return get_order(order_id)


def list_orders(user_id):
    rows = db.fetch_all(
        "SELECT id, user_id, amount, total_amount, discount_amount, user_coupon_id, "
        "       status, pay_type, created_at, paid_at "
        "FROM orders WHERE user_id = %s ORDER BY id DESC",
        (user_id,),
    )
    for r in rows:
        r["amount"] = _money(r["amount"])
        r["total_amount"] = _money(r["total_amount"])
        r["discount_amount"] = _money(r["discount_amount"])
    return rows


def get_order(order_id):
    """查订单详情。

    ⚠️ 缺陷 BUG-004（严重 · 越权）：
      这里只按订单号查询，**没有校验订单属于谁**。
      只要知道订单号，用任何一个已登录账号的 token 都能查到别人的订单。
      取消订单（cancel_order）有同样的问题。
      这类缺陷叫「水平越权 / IDOR」。
    """
    order = db.fetch_one(
        "SELECT id, user_id, amount, total_amount, discount_amount, user_coupon_id, "
        "       status, pay_type, created_at, paid_at "
        "FROM orders WHERE id = %s",
        (order_id,),
    )
    if not order:
        raise ApiError("ORDER_NOT_FOUND", "订单不存在", 404)
    order["amount"] = _money(order["amount"])
    order["total_amount"] = _money(order["total_amount"])
    order["discount_amount"] = _money(order["discount_amount"])
    order["items"] = db.fetch_all(
        "SELECT product_id, product_name, price, quantity "
        "FROM order_items WHERE order_id = %s ORDER BY id",
        (order_id,),
    )
    for it in order["items"]:
        it["price"] = _money(it["price"])

    # 用了券就把券名带上，前端好显示「已优惠 ¥20.00（满100减20）」
    if order["user_coupon_id"]:
        row = db.fetch_one(
            "SELECT c.name FROM user_coupons uc JOIN coupons c ON c.id = uc.coupon_id "
            "WHERE uc.id = %s",
            (order["user_coupon_id"],),
        )
        order["coupon_name"] = row["name"] if row else None
    else:
        order["coupon_name"] = None
    return order


def pay_order(order_id, pay_type=None):
    """支付订单。

    ✅ 已修复（原 BUG-001 · 高 · 状态机）：
      修复前直接改状态、不校验订单当前状态，
      一笔已经**取消**的订单仍可被支付成功（CANCELLED -> PAID），
      造成「钱收了、库存没扣」的账实不符。
      现在只有 PENDING 允许支付，其余一律 400 INVALID_STATUS。
      回归用例：tests/bugs/test_bug_order_state.py
    """
    order = db.fetch_one("SELECT id, status FROM orders WHERE id = %s", (order_id,))
    if not order:
        raise ApiError("ORDER_NOT_FOUND", "订单不存在", 404)

    if order["status"] != ORDER_PENDING:
        raise ApiError(
            "INVALID_STATUS",
            "订单当前状态为 %s，不可支付" % order["status"],
            400,
        )

    db.execute(
        "UPDATE orders SET status = %s, pay_type = %s, paid_at = NOW() WHERE id = %s",
        (ORDER_PAID, pay_type or "ALIPAY", order_id),
    )
    return get_order(order_id)


def cancel_order(order_id):
    """取消订单并回滚库存。

    ⚠️ 缺陷 BUG-002（高 · 幂等性）：
      没有判断订单当前状态。对同一笔订单连续取消两次，
      库存会被 **回滚两次** —— 50 件变成 52 件，凭空多出商品。
      同时，取消一笔已支付的订单也没被拦住。

    ⚠️ 缺陷 BUG-004（同 get_order）：没有校验订单归属，可取消别人的订单。
    """
    order = db.fetch_one(
        "SELECT id, user_coupon_id FROM orders WHERE id = %s", (order_id,)
    )
    if not order:
        raise ApiError("ORDER_NOT_FOUND", "订单不存在", 404)

    items = db.fetch_all(
        "SELECT product_id, quantity FROM order_items WHERE order_id = %s", (order_id,)
    )

    db.execute("UPDATE orders SET status = %s WHERE id = %s", (ORDER_CANCELLED, order_id))

    # 退券：订单取消了，券要还给用户，不然这张券就被「吞」了。
    # （注意：因为 BUG-002 允许重复取消，这段也会被执行多次，
    #   好在「退回 UNUSED」本身是幂等的，不会把券变成两张。）
    if order["user_coupon_id"]:
        db.execute(
            "UPDATE user_coupons SET status = %s, order_id = NULL, used_at = NULL "
            "WHERE id = %s",
            (UC_UNUSED, order["user_coupon_id"]),
        )

    for it in items:
        db.execute(
            "UPDATE products SET stock = stock + %s WHERE id = %s",
            (it["quantity"], it["product_id"]),
        )
        db.execute(
            "INSERT INTO stock_logs (product_id, change_qty, reason, order_id) "
            "VALUES (%s, %s, 'ORDER_CANCEL', %s)",
            (it["product_id"], it["quantity"], order_id),
        )

    return get_order(order_id)
