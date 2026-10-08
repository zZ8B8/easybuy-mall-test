# -*- coding: utf-8 -*-
"""易淘商城 · 业务逻辑层

所有业务规则都在这个文件里。接口层（app.py）只负责解析请求、调用这里、返回 JSON。

⚠️ 本项目是「测试靶场」：下面标注了 4 处**刻意保留的缺陷**，
   它们在代码里没有任何特殊标记，需要靠测试用例去发现。
   缺陷清单见 docs/缺陷报告.md。
"""
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
#  订单
# ==================================================================
def create_order(user_id, cart_ids):
    """下单：校验库存 -> 扣库存 -> 生成订单。

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

    # ---- 第一步：逐个读商品、校验（这是非锁定的普通查询）----
    checked = []
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

    # ---- 第二步：扣减库存（与第一步之间没有事务保护，缺陷所在）----
    # 这两步之间隔着一次数据库往返与线程调度，正是这段间隙让并发竞态成立。
    # 靶场把这段延迟显式化，保证缺陷稳定复现；改成 0 可观察窗口消失后的表现。
    db.simulate_round_trip()

    amount = decimal.Decimal("0.00")
    for product, qty in checked:
        db.execute(
            "UPDATE products SET stock = stock - %s WHERE id = %s",
            (qty, product["id"]),
        )
        amount += decimal.Decimal(str(product["price"])) * qty

    # ---- 第三步：落订单 ----
    order_id = db.execute(
        "INSERT INTO orders (user_id, amount, status) VALUES (%s, %s, %s)",
        (user_id, amount, ORDER_PENDING),
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

    # ---- 第四步：清掉已下单的购物车行 ----
    for c in cart_rows:
        db.execute("DELETE FROM carts WHERE id = %s", (c["id"],))

    return get_order(order_id)


def list_orders(user_id):
    rows = db.fetch_all(
        "SELECT id, user_id, amount, status, pay_type, created_at, paid_at "
        "FROM orders WHERE user_id = %s ORDER BY id DESC",
        (user_id,),
    )
    for r in rows:
        r["amount"] = _money(r["amount"])
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
        "SELECT id, user_id, amount, status, pay_type, created_at, paid_at "
        "FROM orders WHERE id = %s",
        (order_id,),
    )
    if not order:
        raise ApiError("ORDER_NOT_FOUND", "订单不存在", 404)
    order["amount"] = _money(order["amount"])
    order["items"] = db.fetch_all(
        "SELECT product_id, product_name, price, quantity "
        "FROM order_items WHERE order_id = %s ORDER BY id",
        (order_id,),
    )
    for it in order["items"]:
        it["price"] = _money(it["price"])
    return order


def pay_order(order_id, pay_type=None):
    """支付订单。

    ⚠️ 缺陷 BUG-001（高 · 状态机）：
      这里直接改状态，没有先检查订单当前状态。
      所以一笔已经 **取消** 的订单，仍然可以被支付成功（PENDING->PAID 和
      CANCELLED->PAID 都放行了），状态机被打穿。
      正确的做法是：只有 PENDING 状态才允许支付，其余返回 400。
    """
    order = db.fetch_one("SELECT id, status FROM orders WHERE id = %s", (order_id,))
    if not order:
        raise ApiError("ORDER_NOT_FOUND", "订单不存在", 404)

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
    order = db.fetch_one("SELECT id FROM orders WHERE id = %s", (order_id,))
    if not order:
        raise ApiError("ORDER_NOT_FOUND", "订单不存在", 404)

    items = db.fetch_all(
        "SELECT product_id, quantity FROM order_items WHERE order_id = %s", (order_id,)
    )

    db.execute("UPDATE orders SET status = %s WHERE id = %s", (ORDER_CANCELLED, order_id))

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
