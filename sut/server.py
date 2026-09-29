# -*- coding: utf-8 -*-
"""易淘商城 · HTTP 接口层

用标准库 http.server 实现，零第三方依赖，克隆下来直接就能跑：

    python sut/server.py            # 监听 127.0.0.1:5001
    python sut/server.py 8080       # 指定端口

统一响应格式：
    成功  {"code": "OK", "data": ...}
    失败  {"code": "错误码", "message": "错误描述"}
"""
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

if __package__ in (None, ""):
    sys.path.insert(0, __file__.rsplit("sut", 1)[0])
    from sut import service
    from sut.service import BizError
else:
    from . import service
    from .service import BizError


DEFAULT_PORT = 5001


class Router(object):
    """极简路由：把 (method, path_pattern) 映射到处理函数。"""

    def __init__(self):
        self.rules = []

    def add(self, method, pattern, handler, auth=False):
        regex = re.compile("^" + pattern.replace("{id}", "(?P<id>[^/]+)") + "$")
        self.rules.append((method, regex, handler, auth))

    def match(self, method, path):
        for m, regex, handler, auth in self.rules:
            if m != method:
                continue
            found = regex.match(path)
            if found:
                return handler, found.groupdict(), auth
        return None, None, None


router = Router()


def route(method, pattern, auth=False):
    def wrapper(func):
        router.add(method, pattern, func, auth)
        return func
    return wrapper


# --------------------------------------------------------------------------
# 接口实现
# --------------------------------------------------------------------------
@route("GET", "/health")
def health(ctx):
    return {"status": "UP"}


@route("POST", "/api/user/register")
def api_register(ctx):
    body = ctx["body"]
    user = service.register(
        body.get("username"), body.get("password"), body.get("phone"))
    return {"userId": user["id"], "username": user["username"]}


@route("POST", "/api/user/login")
def api_login(ctx):
    body = ctx["body"]
    token = service.login(body.get("username"), body.get("password"))
    return {"token": token}


@route("GET", "/api/products")
def api_products(ctx):
    query = ctx["query"]
    page = int(query.get("page", ["1"])[0])
    size = int(query.get("size", ["10"])[0])
    category = query.get("category", [None])[0]
    return service.list_products(page, size, category)


@route("GET", "/api/products/{id}")
def api_product_detail(ctx):
    return service.get_product(ctx["params"]["id"])


@route("POST", "/api/cart/items", auth=True)
def api_cart_add(ctx):
    body = ctx["body"]
    product_id = body.get("productId")
    quantity = body.get("quantity")
    row = service.add_to_cart(ctx["user"]["id"], product_id, quantity)
    return {"cartId": row["id"], "quantity": row["quantity"]}


@route("GET", "/api/cart/items", auth=True)
def api_cart_list(ctx):
    return {"items": service.list_cart(ctx["user"]["id"])}


@route("PUT", "/api/cart/items/{id}", auth=True)
def api_cart_update(ctx):
    row = service.update_cart_quantity(
        ctx["params"]["id"], ctx["body"].get("quantity"))
    return {"cartId": row["id"], "quantity": row["quantity"]}


@route("DELETE", "/api/cart/items/{id}", auth=True)
def api_cart_remove(ctx):
    return service.remove_cart_item(ctx["params"]["id"])


@route("POST", "/api/orders", auth=True)
def api_order_create(ctx):
    return service.create_order(
        ctx["user"]["id"], ctx["body"].get("cartIds") or [])


@route("GET", "/api/orders", auth=True)
def api_order_list(ctx):
    return {"items": service.list_orders(ctx["user"]["id"])}


@route("GET", "/api/orders/{id}", auth=True)
def api_order_detail(ctx):
    return service.get_order(ctx["params"]["id"])


@route("POST", "/api/orders/{id}/pay", auth=True)
def api_order_pay(ctx):
    return service.pay_order(ctx["params"]["id"], ctx["body"].get("payType"))


@route("POST", "/api/orders/{id}/cancel", auth=True)
def api_order_cancel(ctx):
    return service.cancel_order(ctx["params"]["id"])


# --------------------------------------------------------------------------
# HTTP 处理
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if self.server.verbose:
            sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    # -- 辅助 --------------------------------------------------------------
    def _send(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise BizError("INVALID_JSON", "请求体不是合法的 JSON", 400)

    def _dispatch(self, method):
        parsed = urlparse(self.path)
        handler, params, auth_required = router.match(method, parsed.path)
        if handler is None:
            self._send(404, {"code": "NOT_FOUND", "message": "接口不存在"})
            return

        try:
            ctx = {
                "body": self._read_body(),
                "query": parse_qs(parsed.query),
                "params": params,
                "method": method,
            }
            if auth_required:
                token = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
                ctx["user"] = service.current_user(token)
            data = handler(ctx)
            self._send(200, {"code": "OK", "data": data})
        except BizError as e:
            self._send(e.http_status, {"code": e.code, "message": e.message})
        except Exception as e:                       # noqa: BLE001
            self._send(500, {"code": "INTERNAL_ERROR", "message": str(e)})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")


def create_server(port=DEFAULT_PORT, verbose=False):
    """创建服务实例。port=0 时由系统分配空闲端口（测试用）。"""
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    httpd.verbose = verbose
    return httpd


def run_in_thread(port=0, verbose=False):
    """在后台线程启动服务，返回 (httpd, base_url)。"""
    httpd = create_server(port, verbose)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, "http://127.0.0.1:%d" % httpd.server_address[1]


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    httpd = create_server(port, verbose=True)
    print("易淘商城接口服务已启动：http://127.0.0.1:%d" % httpd.server_address[1])
    print("健康检查：/health   接口文档：docs/接口文档.md")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
