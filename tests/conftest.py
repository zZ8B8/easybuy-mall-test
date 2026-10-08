# -*- coding: utf-8 -*-
"""易淘商城 · pytest 公共 fixture

测试跑的是**真实 HTTP 服务**（werkzeug 起在独立端口），不是 Flask 的测试客户端 ——
这样测到的行为和你在浏览器 / Postman 里点出来的完全一致。

独立性保证：每个用例执行前自动把数据库恢复到初始状态，
用例之间不会互相污染，可以任意顺序、任意次数重跑。
"""
import os
import sys
import threading
import time

import pytest
from werkzeug.serving import make_server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import init_db  # noqa: E402
from tests.client import ApiClient  # noqa: E402

TEST_PORT = 5011
BASE_URL = "http://127.0.0.1:%d" % TEST_PORT


class _ServerThread(threading.Thread):
    def __init__(self, app, port):
        super().__init__(daemon=True)
        self._srv = make_server("127.0.0.1", port, app, threaded=True)

    def run(self):
        self._srv.serve_forever()

    def stop(self):
        self._srv.shutdown()


# ----------------------------------------------------------------------
# 整个测试会话共用一个服务进程
# ----------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def server():
    from app import app

    thread = _ServerThread(app, TEST_PORT)
    thread.start()
    time.sleep(0.8)          # 等服务真正开始监听
    yield BASE_URL
    thread.stop()


# ----------------------------------------------------------------------
# 每个用例前重置数据
# ----------------------------------------------------------------------
@pytest.fixture(autouse=True)
def fresh_data(server):
    """把数据库恢复到 sql/seed.sql 定义的初始状态。"""
    init_db.reset_data()
    yield


@pytest.fixture
def api(server):
    """一个未登录的客户端。"""
    return ApiClient(BASE_URL)


@pytest.fixture
def client(server):
    return ApiClient(BASE_URL)


@pytest.fixture
def user_a(server):
    """已登录的 user_a。"""
    c = ApiClient(BASE_URL)
    c.login("user_a")
    return c


@pytest.fixture
def user_b(server):
    """已登录的 user_b。"""
    c = ApiClient(BASE_URL)
    c.login("user_b")
    return c


# ----------------------------------------------------------------------
# 数据库直连查询（做数据一致性校验用）
# ----------------------------------------------------------------------
@pytest.fixture
def db():
    """直接查数据库，用来核对接口返回的数据是不是真的落库了。

    ⚠️ 必须开 autocommit：
       MySQL 的默认隔离级别是 REPEATABLE READ，不开 autocommit 的话
       这个连接上第一次 SELECT 会建立事务快照，之后再查都读的是旧数据 ——
       你会看到「接口明明改了库，直连查询却纹丝不动」的假象。
    """
    import pymysql
    import config

    conn = pymysql.connect(autocommit=True, **config.DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def stock_of(db, product_id):
    """读某商品当前库存。"""
    with db.cursor() as cur:
        cur.execute("SELECT stock FROM products WHERE id = %s", (product_id,))
        row = cur.fetchone()
        return row[0] if row else None


def order_status(db, order_id):
    """读某订单当前状态。"""
    with db.cursor() as cur:
        cur.execute("SELECT status FROM orders WHERE id = %s", (order_id,))
        row = cur.fetchone()
        return row[0] if row else None
