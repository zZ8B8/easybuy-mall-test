# 易淘商城 easybuy-mall

一个完整的 B2C 电商系统，用作**软件测试练习靶场**：能真实下单、扣库存、支付、取消，
也能真实地把库存扣成负数、把已取消的订单支付成功。

- 前端：原生 HTML + CSS + JavaScript（页面渲染 + 调用接口，无需 npm 构建）
- 后端：Python Flask（页面路由 + JSON 接口）
- 数据库：MySQL / MariaDB（7 张表，真实外键与事务）
- 测试：pytest（105 条用例：92 通过 + 13 预期失败，对应 5 个刻意埋入的缺陷）

---

## 一、快速开始

### 1. 环境要求

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.9+ | 建议 3.11 以上 |
| MySQL / MariaDB | 5.7+ / 10.4+ | 本项目在 MariaDB 10.4.14 上验证通过 |
| 浏览器 | 任意现代浏览器 | Chrome / Edge 均可 |

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置数据库连接

数据库地址、账号密码都在 `config.py` 里，默认值：

```
host = 127.0.0.1    port = 3306
user = root         password = 123456
database = easybuy_mall
```

如果你的 MySQL 密码不是 `123456`，改 `config.py`，或者设环境变量 `EASYBUY_DB_PASSWORD`。

### 4. 初始化数据库（建库 + 建表 + 灌初始数据）

```bash
python init_db.py
```

看到 `初始化完成` 即可。这一步会创建 `easybuy_mall` 库、7 张表，并写入 3 个用户和 6 个商品。

### 5. 启动服务

```bash
python app.py
```

浏览器打开 **http://127.0.0.1:5001/** 即可看到商城首页。

---

## 二、测试账号

| 用户名 | 密码 | 说明 |
| --- | --- | --- |
| `demo` | `123456` | 演示账号 |
| `user_a` | `123456` | 越权测试用（A 的订单不该被 B 看到） |
| `user_b` | `123456` | 越权测试用 |

---

## 三、页面功能

| 页面 | 地址 | 功能 |
| --- | --- | --- |
| 商城首页 | `/` | 商品列表、分类筛选、分页、快捷加购 |
| 商品详情 | `/product/<id>` | 商品详情、按数量加购 |
| 登录注册 | `/login` | 登录 / 注册，token 存 localStorage |
| 购物车 | `/cart` | 勾选、改数量、删除、去结算 |
| 我的订单 | `/orders` | 订单列表、支付、取消、查看明细 |

> 想手工试缺陷：首页进「移动电源」（初始库存 3 件），开两个浏览器窗口同时下单，
> 或者把同一笔订单点两次「取消」。具体步骤见 `docs/05-缺陷报告.md`。

---

## 四、目录结构

```
easybuy-mall-test/
├── app.py                # Web 服务入口：页面路由 + JSON 接口
├── service.py            # 业务逻辑层（5 处缺陷埋在这里，无特殊标记）
├── db.py                 # 数据库访问层：连接池 + 查询封装
├── config.py             # 数据库 / 服务 / 并发参数配置
├── init_db.py            # 建库建表灌数据 / 恢复初始数据
├── requirements.txt
├── pytest.ini
├── sql/
│   ├── schema.sql        # 建库建表（7 张表）
│   └── seed.sql          # 初始数据（3 用户 / 6 商品 / 库存流水）
├── templates/            # Jinja2 页面模板
│   ├── base.html  index.html  product.html
│   ├── login.html cart.html   orders.html  404.html
├── static/
│   ├── style.css         # 全站样式
│   └── app.js            # 前端公共库（API 封装 / 登录态 / 工具函数）
├── tools/
│   └── verify_bugs.py    # 一键复现 5 个缺陷并打印证据
├── tests/                # pytest 测试套件（105 条）
│   ├── conftest.py       # 测试夹具：起服务、重置数据、客户端
│   ├── client.py         # 无第三方依赖的接口客户端
│   ├── test_user.py      # 用户模块（23 条）
│   ├── test_product.py   # 商品模块（24 条）
│   ├── test_cart.py      # 购物车模块（19 条）
│   ├── test_order.py     # 订单模块（26 条 + 1 预期失败）
│   └── bugs/             # 5 个缺陷的回归用例（12 条，全部预期失败）
└── docs/                 # 测试文档（需求 / 接口 / 计划 / 用例 / 缺陷 / 报告）
```

---

## 五、如何做测试（三条主线）

### 1. 黑盒手工测试

启动服务后在浏览器里按 `docs/04-测试用例.md` 逐条执行，用 Excel 记录实际结果。
接口层用 **Postman / Apifox**：导入 `docs/02-接口文档.md` 里的接口。
抓包用 **Fiddler**：观察请求头、token、参数、响应体。
查数据用 **Navicat**：连 `127.0.0.1:3306` / root / 123456，看 `easybuy_mall` 库。

重置数据（不用重启服务）：

```bash
python init_db.py reset
# 或接口：POST http://127.0.0.1:5001/api/dev/reset
```

### 2. 自动化测试

```bash
pytest                      # 全量
pytest tests/test_order.py  # 单模块
pytest -m "" -k cancel      # 按关键字
pytest --cov=. --cov-report=html   # 看覆盖率
```

测试套件会自己起一个测试服务（127.0.0.1:5011），每执行一条用例前自动重置数据，
所以可以反复跑、结果稳定。**不需要先手工启动 `app.py`**。

### 3. 缺陷验证

`tests/bugs/` 下有 13 条用例，全部用 `xfail(strict=True)` 标记 ——
**预期失败就是通过**：说明缺陷确实存在。哪天缺陷被修好了，用例会变成 `XPASS` 并报错，
提醒你回归用例该更新了。这就是「缺陷即断言」的写法。

想直接看现场证据，用这个脚本（需要服务在跑）：

```bash
python tools/verify_bugs.py   # 一键复现 5 个缺陷，打印期望 vs 实际
```

---

## 六、已知缺陷清单（练习用）

| 编号 | 模块 | 严重度 | 一句话描述 |
| --- | --- | --- | --- |
| BUG-001 | 订单 | 高 | 已取消的订单仍可被支付成功（状态机被打穿） |
| BUG-002 | 订单 | 高 | 同一订单重复取消，库存被重复回滚，凭空多出商品 |
| BUG-003 | 订单 | 严重 | 并发下单时「查库存」与「扣库存」非原子，导致超卖、库存为负 |
| BUG-004 | 订单 | 严重 | 查询/取消订单不校验归属，可越权操作他人订单（IDOR） |
| BUG-005 | 购物车 | 中 | 加购不校验数量，0 / 负数 / 超库存都能加入购物车 |

详细复现步骤、期望结果、实际结果、修复建议见 `docs/05-缺陷报告.md`。

---

## 七、换端口 / 换数据库

```bash
python app.py 8080                    # 换服务端口
EASYBUY_DB_PASSWORD=xxx python app.py # 换数据库密码
EASYBUY_DB_LATENCY=0 pytest tests/bugs/test_bug_stock_concurrency.py
                                      # 关掉人为延迟，观察竞态窗口消失
```

`config.py` 里的 `SIMULATE_DB_LATENCY` 是给并发缺陷用的：
真实系统里「读库存」和「扣库存」之间必然有一次网络往返，正是这段间隙让超卖成立。
本机数据库同机访问太快，窗口小到偶现，所以把延迟显式化，让缺陷**稳定复现**。
