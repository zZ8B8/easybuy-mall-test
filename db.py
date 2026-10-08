# -*- coding: utf-8 -*-
"""易淘商城 · 数据库访问层

只做「拿连接 + 执行 SQL」这一件事，不含业务逻辑。

为什么要有连接池
----------------
本机 MariaDB 建立一次连接约 0.27 秒（`skip_name_resolve=OFF`，每次连接
都会做一次反向 DNS 解析）。如果每个 HTTP 请求都新建连接：

    · 单个请求要 0.3 秒以上，体验很差
    · 20 个并发请求会被串成 5 秒以上，竞态窗口被彻底冲散，
      并发类缺陷（BUG-003）反而测不出来

所以启动时预先建好 N 个连接放进池子，请求来了直接取、用完还。

为什么用 autocommit
-------------------
本项目的业务是一步一步立即生效的。这也正是 BUG-003 能复现的原因 ——
「校验库存」和「扣减库存」之间没有事务保护。
"""
import queue
import threading
import time
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

import config


def connect(with_db=True):
    """新建一个连接（不走连接池）。"""
    cfg = dict(config.DB_CONFIG if with_db else config.DB_CONFIG_NO_DB)
    return pymysql.connect(cursorclass=DictCursor, autocommit=True, **cfg)


class ConnectionPool(object):
    """极简连接池：预建 N 个连接，取用 + 归还。"""

    def __init__(self, size, with_db=True):
        self.size = size
        self.with_db = with_db
        self._free = queue.Queue()
        self._created = 0
        self._lock = threading.Lock()

    def _new_conn(self):
        cfg = dict(config.DB_CONFIG if self.with_db else config.DB_CONFIG_NO_DB)
        return pymysql.connect(cursorclass=DictCursor, autocommit=True, **cfg)

    def warm_up(self, n=None):
        """启动时预建连接，免得第一批请求卡在建连接上。"""
        n = self.size if n is None else n
        for _ in range(n):
            try:
                self._free.put(self._new_conn())
                with self._lock:
                    self._created += 1
            except Exception:
                break

    def acquire(self, timeout=30):
        try:
            return self._free.get_nowait()
        except queue.Empty:
            pass

        # 池子里没有空闲连接：还没到上限就再建一个，否则排队等
        with self._lock:
            if self._created < self.size:
                self._created += 1
                make_new = True
            else:
                make_new = False

        if make_new:
            return self._new_conn()
        return self._free.get(timeout=timeout)

    def release(self, conn):
        """归还连接。连接已断开就丢掉，别把坏连接放回池子。"""
        try:
            conn.ping()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            with self._lock:
                self._created -= 1
            return
        self._free.put(conn)

    def close_all(self):
        while True:
            try:
                self._free.get_nowait().close()
            except Exception:
                break


# ----------------------------------------------------------------------
# 连接池单例
# ----------------------------------------------------------------------
_pools = {}
_pools_lock = threading.Lock()


def get_pool(with_db=True):
    key = "with_db" if with_db else "no_db"
    pool = _pools.get(key)
    if pool is not None:
        return pool
    with _pools_lock:
        pool = _pools.get(key)
        if pool is None:
            pool = ConnectionPool(config.DB_POOL_SIZE, with_db)
            pool.warm_up()
            _pools[key] = pool
    return pool


@contextmanager
def cursor(with_db=True):
    """游标上下文：从池子里借连接，用完归还。

    用法：
        with cursor() as cur:
            cur.execute("SELECT ...")
    """
    pool = get_pool(with_db)
    conn = pool.acquire()
    try:
        cur = conn.cursor()
        try:
            yield cur
        finally:
            cur.close()
    finally:
        pool.release(conn)


# ----------------------------------------------------------------------
# 常用查询封装
# ----------------------------------------------------------------------
def fetch_all(sql, args=None):
    with cursor() as cur:
        cur.execute(sql, args or ())
        return cur.fetchall()


def fetch_one(sql, args=None):
    with cursor() as cur:
        cur.execute(sql, args or ())
        return cur.fetchone()


def execute(sql, args=None):
    """执行写操作，返回自增主键（INSERT）或受影响行数。"""
    with cursor() as cur:
        cur.execute(sql, args or ())
        return cur.lastrowid if cur.lastrowid else cur.rowcount


def ping():
    """探活：数据库连不上要立刻报错，而不是等第一个请求。"""
    with cursor() as cur:
        cur.execute("SELECT VERSION() AS v")
        return cur.fetchone()["v"]


def simulate_round_trip():
    """模拟一次数据库往返延迟。

    真实系统里，「读库存」和「扣库存」之间隔着一次网络往返 + 线程调度。
    本机数据库快到几乎无延迟，竞态窗口随之消失，缺陷会变成偶现 ——
    所以靶场把这段延迟显式化，保证 BUG-003 能被稳定复现。

    延迟时长由 config.SIMULATE_DB_LATENCY 控制，改成 0 就关掉。
    """
    delay = getattr(config, "SIMULATE_DB_LATENCY", 0)
    if delay and delay > 0:
        time.sleep(delay)
