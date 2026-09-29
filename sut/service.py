# -*- coding: utf-8 -*-
"""易淘商城 · 业务逻辑层

所有业务规则集中在这里，server.py 只做 HTTP 适配。

约定：
- 抛 BizError 表示可预期的业务失败，server 层转成对应状态码；
- 订单状态机：PENDING（待支付） / PAID（已支付） / CANCELLED（已取消）。
"""
import time
from datetime import datetime

from .store import store


class BizError(Exception):
    """业务异常：带错误码与建议的 HTTP 状态码。"""

    def __init__(self, code, message, http_status=400):
        super(BizError, self).__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


ORDER_PENDING = "PENDING"
ORDER_PAID = "PAID"
ORDER_CANCELLED = "CANCELLED"

# 模拟「查询库存」与「扣减库存」之间的持久层往返耗时。
# 真实系统里这两步是两条独立的 SQL，中间必然有网络 + 磁盘延迟；
# 下单接口正是在这段窗口里被并发请求穿插，才出现超卖。
DB_ROUND_TRIP = 0.02


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# 用户
# --------------------------------------------------------------------------
def register(username, password, phone):
    """注册用户。"""
    if not username or not password:
        raise BizError("INVALID_PARAM", "用户名与密码不能为空")
    if len(password) < 6:
        raise BizError("WEAK_PASSWORD", "密码长度不能少于 6 位")
    if phone and (len(phone) != 11 or not phone.isdigit()):
        raise BizError("INVALID_PHONE", "手机号格式不正确")
    if username in store.users_by_name:
        raise BizError("USER_EXISTS", "用户名已存在")

    uid = store.next_id("U")
    store.users[uid] = {
        "id": uid,
        "username": username,
        "password": password,
        "phone": phone,
        "created_at": _now(),
    }
    store.users_by_name[username] = uid
    return store.users[uid]


def login(username, password):
    """登录，返回 token。"""
    uid = store.users_by_name.get(username)
    if uid is None:
        raise BizError("LOGIN_FAILED", "用户名或密码错误", 401)
    if store.users[uid]["password"] != password:
        raise BizError("LOGIN_FAILED", "用户名或密码错误", 401)
    token = store.next_id("T")
    store.tokens[token] = uid
    return token


def current_user(token):
    """由 token 反查用户。"""
    uid = store.tokens.get(token or "")
    if uid is None:
        raise BizError("UNAUTHORIZED", "未登录或登录已失效", 401)
    return store.users[uid]


# --------------------------------------------------------------------------
# 商品
# --------------------------------------------------------------------------
def list_products(page, size, category=None):
    """商品列表，分页返回。"""
    items = [p for p in store.products.values() if p["status"] == "ON_SALE"]
    if category:
        items = [p for p in items if p["category"] == category]
    items.sort(key=lambda p: p["id"])

    start = (page - 1) * size
    end = start + size
    return {
        "total": len(items),
        "page": page,
        "size": size,
        "items": items[start:end],
    }


def get_product(product_id):
    product = store.products.get(product_id)
    if product is None:
        raise BizError("PRODUCT_NOT_FOUND", "商品不存在", 404)
    return product


# --------------------------------------------------------------------------
# 购物车
# --------------------------------------------------------------------------
def add_to_cart(user_id, product_id, quantity):
    """加入购物车：同一商品重复加购则累加数量。"""
    product = get_product(product_id)
    if product["status"] != "ON_SALE":
        raise BizError("PRODUCT_OFF_SALE", "商品已下架")

    for cart in store.carts.values():
        if cart["user_id"] == user_id and cart["product_id"] == product_id:
            cart["quantity"] += quantity
            return cart

    cid = store.next_id("C")
    store.carts[cid] = {
        "id": cid,
        "user_id": user_id,
        "product_id": product_id,
        "quantity": quantity,
        "added_at": _now(),
    }
    return store.carts[cid]


def list_cart(user_id):
    """购物车列表（带商品快照）。"""
    rows = [c for c in store.carts.values() if c["user_id"] == user_id]
    rows.sort(key=lambda c: c["id"])
    result = []
    for row in rows:
        product = store.products.get(row["product_id"], {})
        result.append({
            "cart_id": row["id"],
            "product_id": row["product_id"],
            "product_name": product.get("name"),
            "price": product.get("price"),
            "quantity": row["quantity"],
        })
    return result


def update_cart_quantity(cart_id, quantity):
    """修改购物车数量。"""
    cart = store.carts.get(cart_id)
    if cart is None:
        raise BizError("CART_NOT_FOUND", "购物车条目不存在", 404)
    cart["quantity"] = quantity
    return cart


def remove_cart_item(cart_id):
    """删除购物车条目。"""
    cart = store.carts.pop(cart_id, None)
    if cart is None:
        raise BizError("CART_NOT_FOUND", "购物车条目不存在", 404)
    return {"removed": cart_id}


# --------------------------------------------------------------------------
# 订单
# --------------------------------------------------------------------------
def _calc_amount(items):
    """汇总订单金额。"""
    amount = 0.0
    for item in items:
        amount += item["price"] * item["quantity"]
    return amount


def create_order(user_id, cart_ids):
    """提交订单：校验购物车 -> 校验库存 -> 落订单 -> 扣减库存。"""
    if not cart_ids:
        raise BizError("EMPTY_CART", "请先选择要结算的商品")

    carts = []
    for cid in cart_ids:
        cart = store.carts.get(cid)
        if cart is None:
            raise BizError("CART_NOT_FOUND", "购物车条目不存在：%s" % cid, 404)
        carts.append(cart)

    # 先统一校验库存，避免部分商品通过、部分不通过
    order_items = []
    for cart in carts:
        product = store.products[cart["product_id"]]
        if product["stock"] < cart["quantity"]:
            raise BizError(
                "INSUFFICIENT_STOCK",
                "商品[%s]库存不足，当前库存 %d" % (product["name"], product["stock"]),
            )
        order_items.append({
            "product_id": product["id"],
            "product_name": product["name"],
            "price": product["price"],
            "quantity": cart["quantity"],
        })

    oid = store.next_id("O")
    store.orders[oid] = {
        "id": oid,
        "user_id": user_id,
        "items": order_items,
        "amount": _calc_amount(order_items),
        "status": ORDER_PENDING,
        "created_at": _now(),
        "paid_at": None,
        "pay_type": None,
    }

    # 校验通过后统一扣减。
    # 注意：这里与上面的库存校验是分开的两步，中间没有加锁保护 ——
    # 并发请求会在这个窗口里读到同一份旧库存，于是全部通过校验，扣成负数。
    time.sleep(DB_ROUND_TRIP)
    for item in order_items:
        product = store.products[item["product_id"]]
        product["stock"] -= item["quantity"]
        store.stock_logs.append({
            "order_id": oid,
            "product_id": product["id"],
            "change": -item["quantity"],
            "after": product["stock"],
            "at": _now(),
        })

    for cart in carts:
        store.carts.pop(cart["id"], None)

    return store.orders[oid]


def get_order(order_id):
    """查询订单详情。"""
    order = store.orders.get(order_id)
    if order is None:
        raise BizError("ORDER_NOT_FOUND", "订单不存在", 404)
    return order


def list_orders(user_id):
    """我的订单列表。"""
    rows = [o for o in store.orders.values() if o["user_id"] == user_id]
    rows.sort(key=lambda o: o["id"])
    return rows


def pay_order(order_id, pay_type):
    """支付订单。"""
    order = get_order(order_id)
    if pay_type not in ("ALIPAY", "WECHAT", "CARD"):
        raise BizError("INVALID_PAY_TYPE", "不支持的支付方式")

    order["status"] = ORDER_PAID
    order["paid_at"] = _now()
    order["pay_type"] = pay_type
    return order


def cancel_order(order_id):
    """取消订单，并把占用的库存释放回去。"""
    order = get_order(order_id)
    if order["status"] == ORDER_PAID:
        raise BizError("ORDER_PAID", "已支付订单不能取消")

    order["status"] = ORDER_CANCELLED
    for item in order["items"]:
        product = store.products[item["product_id"]]
        product["stock"] += item["quantity"]
        store.stock_logs.append({
            "order_id": order["id"],
            "product_id": item["product_id"],
            "change": item["quantity"],
            "after": product["stock"],
            "at": _now(),
        })
    return order
