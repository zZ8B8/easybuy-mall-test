# -*- coding: utf-8 -*-
"""易淘商城 · Web 服务入口

一个 B2C 电商后端：前端页面 + JSON 接口，数据存在 MySQL。

启动：
    python app.py                  # 监听 127.0.0.1:5001
    python app.py 8080             # 指定端口

统一响应格式：
    成功  {"code": "OK", "data": ...}
    失败  {"code": "错误码", "message": "错误描述"}      HTTP 状态码 4xx
"""
import datetime
import decimal
import sys

from flask import Flask, jsonify, render_template, request

import config
import db
import service
from service import ApiError

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False


# ==================================================================
#  统一的 JSON 序列化
# ==================================================================
def _jsonable(obj):
    """把数据库里取出来的 Decimal / datetime 转成 JSON 能表示的普通类型。"""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, datetime.datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(obj, datetime.date):
        return obj.strftime("%Y-%m-%d")
    return obj


def ok(data=None):
    return jsonify({"code": "OK", "data": _jsonable(data)})


@app.errorhandler(ApiError)
def handle_api_error(err):
    return jsonify({"code": err.code, "message": err.message}), err.http_status


@app.errorhandler(404)
def handle_404(_err):
    # 区分「页面不存在」和「接口不存在」
    if request.path.startswith("/api/"):
        return jsonify({"code": "NOT_FOUND", "message": "接口不存在"}), 404
    return render_template("404.html"), 404


@app.errorhandler(500)
def handle_500(err):
    return jsonify({"code": "INTERNAL_ERROR", "message": str(err)}), 500


# ==================================================================
#  请求解析小工具
# ==================================================================
def body():
    return request.get_json(silent=True) or {}


def token():
    auth = request.headers.get("Authorization", "")
    return auth.replace("Bearer ", "").strip() or None


def auth_user():
    """需要登录的接口统一走这里。"""
    return service.current_user(token())


# ==================================================================
#  页面路由
# ==================================================================
@app.route("/")
def page_index():
    return render_template("index.html")


@app.route("/product/<int:product_id>")
def page_product(product_id):
    return render_template("product.html", product_id=product_id)


@app.route("/login")
def page_login():
    return render_template("login.html")


@app.route("/cart")
def page_cart():
    return render_template("cart.html")


@app.route("/orders")
def page_orders():
    return render_template("orders.html")


@app.route("/coupons")
def page_coupons():
    return render_template("coupons.html")


# ==================================================================
#  接口 · 系统
# ==================================================================
@app.route("/health")
def health():
    return ok({"status": "UP", "db": db.ping()})


@app.route("/api/dev/reset", methods=["POST"])
def dev_reset():
    """把数据恢复到初始状态。

    这是给测试用的便利接口 —— 手工测试时点一下就能回到干净数据，
    不用重启服务。生产环境当然不会有这种接口。
    """
    import init_db

    init_db.reset_data()
    return ok({"reset": True})


# ==================================================================
#  接口 · 用户
# ==================================================================
@app.route("/api/user/register", methods=["POST"])
def api_register():
    b = body()
    user = service.register(b.get("username"), b.get("password"), b.get("phone"))
    return ok({"userId": user["id"], "username": user["username"]})


@app.route("/api/user/login", methods=["POST"])
def api_login():
    b = body()
    return ok({"token": service.login(b.get("username"), b.get("password"))})


@app.route("/api/user/profile")
def api_profile():
    user = auth_user()
    return ok(user)


# ==================================================================
#  接口 · 商品
# ==================================================================
@app.route("/api/products")
def api_products():
    q = request.args
    page = int(q.get("page") or 1)
    size = int(q.get("size") or 10)
    return ok(service.list_products(page, size, q.get("category")))


@app.route("/api/products/<int:product_id>")
def api_product_detail(product_id):
    return ok(service.get_product(product_id))


# ==================================================================
#  接口 · 购物车
# ==================================================================
@app.route("/api/cart/items", methods=["POST"])
def api_cart_add():
    user = auth_user()
    b = body()
    row = service.add_to_cart(user["id"], b.get("productId"), b.get("quantity"))
    return ok({"cartId": row["id"], "quantity": row["quantity"]})


@app.route("/api/cart/items")
def api_cart_list():
    user = auth_user()
    return ok({"items": service.list_cart(user["id"])})


@app.route("/api/cart/items/<int:cart_id>", methods=["PUT"])
def api_cart_update(cart_id):
    user = auth_user()
    return ok(service.update_cart_quantity(user["id"], cart_id, body().get("quantity")))


@app.route("/api/cart/items/<int:cart_id>", methods=["DELETE"])
def api_cart_remove(cart_id):
    user = auth_user()
    return ok(service.remove_cart_item(user["id"], cart_id))


# ==================================================================
#  接口 · 优惠券
# ==================================================================
@app.route("/api/coupons")
def api_coupon_list():
    return ok({"items": service.list_coupons()})


@app.route("/api/coupons/<int:coupon_id>/claim", methods=["POST"])
def api_coupon_claim(coupon_id):
    user = auth_user()
    return ok(service.claim_coupon(user["id"], coupon_id))


@app.route("/api/user/coupons")
def api_my_coupons():
    user = auth_user()
    return ok({"items": service.list_user_coupons(user["id"], request.args.get("status"))})


# ==================================================================
#  接口 · 订单
# ==================================================================
@app.route("/api/orders", methods=["POST"])
def api_order_create():
    user = auth_user()
    b = body()
    return ok(service.create_order(
        user["id"], b.get("cartIds") or [], b.get("userCouponId")
    ))


@app.route("/api/orders")
def api_order_list():
    user = auth_user()
    return ok({"items": service.list_orders(user["id"])})


@app.route("/api/orders/<int:order_id>")
def api_order_detail(order_id):
    return ok(service.get_order(order_id))


@app.route("/api/orders/<int:order_id>/pay", methods=["POST"])
def api_order_pay(order_id):
    return ok(service.pay_order(order_id, body().get("payType")))


@app.route("/api/orders/<int:order_id>/cancel", methods=["POST"])
def api_order_cancel(order_id):
    return ok(service.cancel_order(order_id))


# ==================================================================
#  启动
# ==================================================================
def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else config.SERVER_PORT

    try:
        ver = db.ping()
    except Exception as exc:  # noqa: BLE001
        print("")
        print("  [错误] 连不上数据库：%s" % exc)
        print("  请先确认 MySQL 已启动，然后运行：python init_db.py")
        print("")
        sys.exit(1)

    print("=" * 62)
    print("  易淘商城 · 服务已启动")
    print("=" * 62)
    print("  数据库   ：MySQL %s @ %s:%s/%s" % (
        ver, config.DB_CONFIG["host"], config.DB_CONFIG["port"],
        config.DB_CONFIG["database"]))
    print("  商城首页 ：http://127.0.0.1:%d/" % port)
    print("  健康检查 ：http://127.0.0.1:%d/health" % port)
    print("  接口文档 ：docs/02-接口文档.md")
    print("-" * 62)
    print("  按 Ctrl+C 停止服务")
    print("=" * 62)
    app.run(host=config.SERVER_HOST, port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
