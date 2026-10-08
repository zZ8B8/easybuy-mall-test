# -*- coding: utf-8 -*-
"""易淘商城 · 配置

数据库连接信息集中在这里。想换数据库地址 / 密码，
改下面的默认值，或者设置对应的环境变量（环境变量优先级更高）。
"""
import os

# ------------------------------------------------------------
# 数据库
# ------------------------------------------------------------
DB_CONFIG = {
    "host":     os.environ.get("EASYBUY_DB_HOST", "127.0.0.1"),
    "port":     int(os.environ.get("EASYBUY_DB_PORT", "3306")),
    "user":     os.environ.get("EASYBUY_DB_USER", "root"),
    "password": os.environ.get("EASYBUY_DB_PASSWORD", "123456"),
    "database": os.environ.get("EASYBUY_DB_NAME", "easybuy_mall"),
    "charset":  "utf8mb4",
}

# 不带库名，用于建库（建库时库还不存在）
DB_CONFIG_NO_DB = {k: v for k, v in DB_CONFIG.items() if k != "database"}

# 连接池大小。
# 为什么要连接池：本机 MariaDB 建一次连接要 ~0.27 秒（skip_name_resolve=OFF
# 时会做反向 DNS 解析），如果每个 HTTP 请求都新建连接，
# 20 个并发请求会被串行化到 5 秒以上 —— 既慢，又会把并发测试的窗口冲散。
# 用连接池复用 + 启动时预热，请求处理就能降到毫秒级。
DB_POOL_SIZE = int(os.environ.get("EASYBUY_DB_POOL", "20"))

# ------------------------------------------------------------
# 服务
# ------------------------------------------------------------
SERVER_HOST = os.environ.get("EASYBUY_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("EASYBUY_PORT", "5001"))

# 下单时单笔最大数量（业务规则，用于边界值测试）
MAX_ORDER_QUANTITY = 99

# ------------------------------------------------------------
# 并发缺陷复现用的「数据库往返延迟」（秒）
# ------------------------------------------------------------
# 真实系统里，「查库存」和「扣库存」是两次独立的数据库交互，
# 中间必然隔着一次网络往返 + 线程调度，正是这段时间让并发竞态得以发生。
#
# 本机数据库太快（同机、内存命中），这个窗口小到跑十次才中一次，
# 缺陷会变成「偶现」，没法写进回归测试。
# 所以这里把那段延迟显式化，让缺陷 **稳定复现**。
#
# 想观察「没有这个延迟会怎样」，把它改成 0 再跑一次并发用例即可。
SIMULATE_DB_LATENCY = float(os.environ.get("EASYBUY_DB_LATENCY", "0.05"))
