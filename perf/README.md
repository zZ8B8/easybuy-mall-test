# 性能测试（JMeter）

这里是易淘商城的性能测试脚本与原始结果。完整分析见 [`../docs/07-性能测试报告.md`](../docs/07-性能测试报告.md)。

## 目录

| 文件 | 说明 |
| --- | --- |
| `easybuy-perf.jmx` | JMeter 测试计划（2 个线程组：只读查询 / 登录+加购） |
| `run_perf.bat` | 一键跑三组并发梯度（Windows） |
| `results/*.jtl` | JMeter 原始采样结果（CSV，可用 Excel 直接打开） |
| `charts/*.png` | 结果图 |

## 前置条件

1. **Apache JMeter 5.6.x**（需 JDK 8+）。解压后把 `bin` 目录加进 `PATH`，或设置环境变量 `JMETER_HOME`。
2. 被测服务已启动：`python app.py`（默认 <http://127.0.0.1:5001>）。
3. 数据库里有演示账号：先跑一次 `python demo_data.py`（生成 `user_01` ~ `user_30`，密码均为 `123456`）。
   写场景按线程号取账号，没有这批账号时登录会返回 401。

> 如果机器页面文件较小，JMeter 默认的 1G 堆会起不来（报 `os::commit_memory ... 页面文件太小`）。
> 可以先 `set HEAP=-Xms128m -Xmx384m -XX:MaxMetaspaceSize=128m` 再启动；`run_perf.bat` 已默认做了这件事。

## 怎么跑

```bat
rem 方式一：一键跑三组
perf\run_perf.bat

rem 方式二：手动指定并发（threads=并发线程数, loops=每个线程循环次数）
jmeter -n -t perf\easybuy-perf.jmx -l perf\results\my.jtl -Jthreads=50 -Jloops=40
```

可用参数（都可以用 `-J名字=值` 覆盖）：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `host` | 127.0.0.1 | 被测服务地址 |
| `port` | 5001 | 被测服务端口 |
| `threads` / `loops` | 20 / 40 | 只读线程组的并发与循环 |
| `wthreads` / `wloops` | 20 / 10 | 读写混合线程组的并发与循环 |

## 测试计划做了什么

| 线程组 | 接口 | 说明 |
| --- | --- | --- |
| ① 只读 · 商品列表查询 | `GET /api/products?page=1&size=10` | 带断言（响应里必须含 `"code":"OK"`）；该线程组并发数用 `-Jthreads` 控制 |
| ② 读写混合 · 登录 + 加购 | `POST /api/user/login` → `POST /api/cart/items` | 先登录并提取 `$.data.token`，再带 `Authorization: Bearer` 加购；账号按线程号取 `user_01`… |

## 已跑过的结果

`results/` 里的文件对应报告中的三组结论：

| 文件 | 场景 |
| --- | --- |
| `run-1.jtl` | 1 线程基线（`-Jthreads=1 -Jloops=30`） |
| `run-a.jtl` | 20 并发（`-Jthreads=20 -Jloops=40`） |
| `run-b.jtl` | 50 并发（`-Jthreads=50 -Jloops=40`） |
| `run-b2.jtl` | 50 并发复测（与 run-b 同参数，验证稳定性） |
| `run-b2-pool40.jtl` | 连接池调到 40 后的 50 并发（调优验证，`EASYBUY_DB_POOL=40`） |

以上都跑在**同一个服务进程**里，每次测量前先跑一轮预热（20 线程 × 5 循环，结果丢弃）。
实测未预热时 TPS 只有预热后的 40%~45%，冷启动会严重污染结果。

> 说明：压测机与被测服务在同一台机器上（本机 8 核），压测进程本身会抢占 CPU，
> 因此这里的绝对 TPS 偏保守，只能用于横向对比与瓶颈定位，不能当作生产容量。
