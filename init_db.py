# -*- coding: utf-8 -*-
"""易淘商城 · 数据库初始化

两个用途：
    1. 首次部署：双击「一键启动.bat」时会自动调用，建库 + 建表 + 灌初始数据
    2. 跑测试前：pytest 每个用例前调用 reset_data()，把数据恢复到初始状态

命令行用法：
    python init_db.py          # 建库建表 + 灌数据
    python init_db.py reset    # 只灌数据（保留表结构）
"""
import io
import os
import sys

import db

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(HERE, "sql", "schema.sql")
SEED = os.path.join(HERE, "sql", "seed.sql")


def _statements(path):
    """把 .sql 文件拆成一条条语句（先去掉整行注释，避免注释里的符号干扰）。"""
    with io.open(path, encoding="utf-8") as f:
        text = f.read()
    lines = []
    for ln in text.splitlines():
        if ln.strip().startswith("--"):
            continue
        lines.append(ln)
    text = "\n".join(lines)
    return [s.strip() for s in text.split(";") if s.strip()]


def _run(path, with_db):
    """在一个独立连接上顺序执行整个 .sql 文件。

    这里刻意不走连接池：建库脚本会切库（USE）、会改连接状态，
    需要一个干净、专用、用完就关的连接。
    """
    stmts = _statements(path)
    conn = db.connect(with_db)
    try:
        with conn.cursor() as cur:
            for s in stmts:
                cur.execute(s)
    finally:
        conn.close()
    return len(stmts)


def init_database():
    """建库 + 建表 + 灌初始数据。可重复执行（会先删旧表）。"""
    n1 = _run(SCHEMA, with_db=False)
    n2 = _run(SEED, with_db=True)
    print("  建库建表：执行 %d 条语句" % n1)
    print("  初始数据：执行 %d 条语句" % n2)


def reset_data():
    """只把数据恢复到初始状态（表结构不动）。测试用例之间调用。"""
    _run(SEED, with_db=True)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "reset":
        reset_data()
        print("  数据已重置为初始状态。")
    else:
        init_database()
        print("  数据库初始化完成。")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print("")
        print("  [错误] 数据库初始化失败：%s" % exc)
        print("  请检查：")
        print("    1) MySQL 服务是否已启动（服务名一般为 MySQL84）")
        print("    2) config.py 里的账号密码是否正确")
        print("    3) 端口 3306 是否被占用")
        sys.exit(1)
