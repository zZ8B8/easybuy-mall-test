# -*- coding: utf-8 -*-
"""易淘商城 · 内存数据层

用 Python 字典模拟关系库的表，进程内共享。不依赖任何数据库服务，
克隆下来直接就能跑；进程退出后数据重置。

"表"结构：
    users           用户
    products        商品（含库存）
    carts           购物车明细
    orders          订单（items 内嵌订单明细）
    stock_logs      库存流水（审计用）
    tokens          登录令牌
"""
import itertools


class Store(object):
    def __init__(self):
        self.reset()

    def reset(self):
        """清空并重新装载基础数据。测试中每个用例前会调用。"""
        self.users = {}           # user_id -> dict
        self.users_by_name = {}   # username -> user_id
        self.products = {}        # product_id -> dict
        self.carts = {}           # cart_id -> dict
        self.orders = {}          # order_id -> dict
        self.stock_logs = []      # 库存流水
        self.tokens = {}          # token -> user_id
        self._seq = itertools.count(1)
        self._seed_products()

    def next_id(self, prefix):
        """业务主键生成器，形如 P00007 / O00031。"""
        return "%s%05d" % (prefix, next(self._seq))

    def _seed_products(self):
        """预置商品。库存是刻意留得比较少，方便观察边界行为。"""
        goods = [
            ("数码", "无线蓝牙耳机",         199.00, 50),
            ("数码", "机械键盘 87 键",       329.50, 8),
            ("数码", "移动电源 20000mAh",    129.00, 3),
            ("服饰", "纯棉短袖 T 恤",         59.90, 100),
            ("服饰", "经典帆布鞋",           189.00, 20),
            ("食品", "每日坚果礼盒 750g",     99.99, 5),
        ]
        for cat, name, price, stock in goods:
            pid = self.next_id("P")
            self.products[pid] = {
                "id": pid,
                "name": name,
                "category": cat,
                "price": price,
                "stock": stock,
                "status": "ON_SALE",
            }


# 全局单例：整个服务共用一个 Store
store = Store()
