---
name: observer-ref
description: 编写 observer 模块（全天候可观测性与异常感知）功能时自动加载的参考指南。当你需要实现容器生命周期看门狗、日志流滑动窗口、业务水位巡检、事件防抖等 observer/ 下任何功能时，务必先阅读本技能中的参考项目指引，从 docker-py 和 mc-server-runner 中找到经过验证的 API 用法和设计模式再动手。
---

# Observer 模块参考指南

编写 `observer/` 模块功能时，核心依赖是 docker-py 的容器监控 API。所有参考项目位于 `references/` 目录。

## 子任务速查表

| 子任务 | 子目录 | 你在写什么 | 核心参考项目 |
|--------|--------|-----------|-------------|
| 一 | `watchdog/` | 生命周期看门狗（容器 Exited/OOMKilled） | docker-py |
| 二 | `logstream/` | 日志流滑动窗口（正则匹配 + Ring Buffer） | docker-py |
| 三 | `metrics/` | 业务水位巡检（CPU/内存/TPS） | docker-py、mc-server-runner |
| 四 | `dispatcher/` | 事件防抖与唤醒（5s 窗口聚合） | 自行设计 |

---

## docker-py 三线程架构

docker-py 是同步库（基于 requests），observer 的四个子任务需要用线程化方式并发运行。推荐的架构：

```
Thread 1: events()       → 生命周期看门狗（极轻量，事件驱动）
Thread 2: logs(stream)   → 日志流滑动窗口（持续读取）
Thread 3: stats(stream)  → 业务水位巡检（~1s 采样间隔）
主线程:   dispatcher     → 事件防抖 + 组装 AnomalyEvent
```

---

## 子任务一：生命周期看门狗 → 读 docker-py events()

**你要读的文件：**

- `references/docker-py/docker/api/daemon.py` — `events()` 方法实现（line 24）
- `references/docker-py/docker/models/containers.py` — Container 模型层，`status` 和 `health` 属性

**关键 API：**

```python
# 监听指定容器的事件流
events = client.events(
    filters={'type': 'container', 'container': container_id},
    decode=True  # 自动解析为 dict
)
for event in events:
    status = event['status']  # 'start', 'stop', 'die', 'oom', 'destroy', 'pause', 'unpause'
    if status == 'oom':
        # OOM Kill 事件 — 生成硬宕机事件
        handle_oom(event)
    elif status == 'die':
        # 容器退出 — 检查 exitCode
        exit_code = event.get('Actor', {}).get('Attributes', {}).get('exitCode')
        if exit_code and int(exit_code) != 0:
            handle_abnormal_exit(event, exit_code)
```

**关键要点：**

1. `events()` 的 `timeout=None` — 连接永久保持，不会超时断开，适合长期监听。
2. `filters` 参数支持按 `type`、`container`、`event`、`image`、`label` 过滤，减少无关事件。
3. 事件格式：`{'from': 'image:tag', 'id': 'container-id', 'status': 'start', 'time': 1423339459}`
4. OOM 事件有两种检测路径：`events()` 的 `status='oom'`（最及时）和 `container.attrs['State']['OOMKilled']`（事后确认）

**硬宕机事件触发条件（对应 PRD）：**
- 容器状态突变为 `Exited`，且 `Exit Code != 0`
- 或 `OOMKilled = True`

---

## 子任务二：日志流滑动窗口 → 读 docker-py logs()

**你要读的文件：**

- `references/docker-py/docker/api/container.py` — `logs()` 方法实现（line 821）
- `references/docker-py/docker/api/client.py` — `_multiplexed_response_stream_helper()` 多路复用帧解析（line 392）
- `references/docker-py/docker/types/daemon.py` — `CancellableStream` 可取消流
- `references/docker-py/docker/utils/json_stream.py` — `split_buffer()` JSON 流拆分

**关键 API：**

```python
# 流式读取容器日志
log_stream = container.logs(
    stream=True,       # 返回生成器而非 bytes
    follow=True,       # 持续跟踪新日志（默认跟随 stream 值）
    stdout=True,
    stderr=True,
    tail=100,          # 先返回最近 100 行历史
    timestamps=True,   # 带时间戳便于后续分析
)
```

**滑动窗口实现模式：**

```python
import collections
import re

# 200 行 Ring Buffer（PRD 要求：报错前 100 行 + 报错后 100 行）
window = collections.deque(maxlen=200)

# 高危报错正则（PRD 要求）
FATAL_PATTERNS = re.compile(
    r'\[FATAL\]|Exception|java\.lang\.OutOfMemoryError|net\.minecraft\.crash'
)

for chunk in log_stream:
    line = chunk.decode('utf-8', errors='replace').rstrip()
    window.append(line)

    if FATAL_PATTERNS.search(line):
        # 冻结队列 — 截取当前窗口内容
        frozen_context = list(window)
        # 继续读取 100 行后续日志
        post_context = []
        for _ in range(100):
            try:
                next_chunk = next(log_stream)
                post_context.append(next_chunk.decode('utf-8', errors='replace').rstrip())
            except StopIteration:
                break
        full_context = frozen_context + post_context
        # 交给 dispatcher
        dispatch_anomaly("hard_crash", full_context)
        break  # 或继续监听
```

**多路复用帧协议**（非 TTY 容器）：
- 8 字节帧头：`>BxxxL` = 1 字节流类型（1=STDOUT, 2=STDERR）+ 3 字节填充 + 4 字节载荷长度
- docker-py 的 `_multiplexed_response_stream_helper()` 已处理此协议，你无需手动解析

**优雅关闭**：从控制线程调用 `log_stream.close()`，迭代线程会收到 `StopIteration`。CancellableStream 通过关闭底层 socket 实现中断。

**日志风暴防御（PRD 边界情况）：**
```python
# 限速阀：单秒读取行数超过阈值直接截断
RATE_LIMIT = 1000  # 每秒最大行数
counter = 0
last_second = time.time()

for chunk in log_stream:
    now = time.time()
    if now - last_second >= 1.0:
        counter = 0
        last_second = now
    counter += 1
    if counter > RATE_LIMIT:
        # 标记 LOG_SPAM_DETECTED，丢弃剩余日志直到下一秒
        continue
    # ... 正常处理
```

---

## 子任务三：业务水位巡检 → 读 docker-py stats()

**你要读的文件：**

- `references/docker-py/docker/api/container.py` — `stats()` 方法实现（line 1139）
- `references/docker-py/tests/unit/fake_stat.py` — Stats 数据结构示例

**关键 API：**

```python
# 流式读取容器资源指标（~1s 采样间隔）
for stat in container.stats(decode=True, stream=True):
    cpu_percent = calculate_cpu_percent(stat)
    mem_percent = stat['memory_stats']['usage'] / stat['memory_stats']['limit'] * 100
    mem_usage = stat['memory_stats']['usage']
    # ... 发送给 dispatcher
```

**CPU 百分比计算**（docker-py 不直接提供，需自行计算）：

```python
def calculate_cpu_percent(stat: dict) -> float:
    """从 docker stats 数据计算 CPU 使用率。"""
    cpu_delta = (
        stat['cpu_stats']['cpu_usage']['total_usage']
        - stat['precpu_stats']['cpu_usage']['total_usage']
    )
    sys_delta = (
        stat['cpu_stats']['system_cpu_usage']
        - stat['precpu_stats']['system_cpu_usage']
    )
    if sys_delta == 0:
        return 0.0
    num_cpus = len(stat['cpu_stats']['cpu_usage'].get('percpu_usage', [1]))
    return (cpu_delta / sys_delta) * num_cpus * 100.0
```

**关键 Stats 字段：**

| 字段 | 用途 |
|------|------|
| `cpu_stats.cpu_usage.total_usage` | CPU 总使用量（需与 precpu_stats 做差值） |
| `cpu_stats.system_cpu_usage` | 系统 CPU 总量（需与 precpu_stats 做差值） |
| `cpu_stats.cpu_usage.percpu_usage` | 每核使用量 |
| `memory_stats.usage` | 当前内存使用 |
| `memory_stats.limit` | 内存限制 |
| `memory_stats.failcnt` | cgroup 内存违规计数（预警 OOM） |
| `memory_stats.max_usage` | 内存峰值 |
| `network.rx_bytes / tx_bytes` | 网络收发字节 |

**TPS 嗅探（PRD 要求）：**
- 方式一：解析日志中的 `Can't keep up! Is the server overloaded?` 警告
- 方式二：通过 RCON 协议发送 `tps` 指令（需配合 `infra/rcon_client.py`）

**软宕机判定（对应 PRD）：**
- CPU 持续 100% 且 TPS 连续 60 秒低于 10.0 → 生成软宕机事件

**静默崩溃兜底（PRD 边界情况）：**
- 连续 3 次 RCON 请求超时无响应 → 无视日志状态，强制触发异常

**OOM 预警三重保险：**
1. `events()` 的 `status='oom'` 事件（最及时）
2. `stats()` 的 `memory_stats.failcnt` 递增（预警）
3. `container.attrs['State']['OOMKilled']`（事后确认）

---

## 子任务四：事件防抖与唤醒

dispatcher 是唯一没有直接参考项目的子任务，需自行设计。

**PRD 要求：**
- 5 秒窗口期内将所有报错合并为一个 AnomalyEvent
- 组装 JSON Payload：时间戳 + 触发原因 + 资源利用率 + 200 行上下文日志
- 通过 HTTP POST 或消息队列推送给 LangGraph

**参考 mc-server-runner 的信号处理模式：**

- `references/mc-server-runner/main.go` — 两阶段优雅关机（SIGTERM → 通知延迟 → stop）的上下文保存思路
- `references/mc-server-runner/memory.go` — OOM 退出码 137 的特殊处理和系统内存诊断

**RCON 双路径命令**（mc-server-runner 的 `sendCommand()` 模式）：
```python
# 优先 RCON，RCON 不可用时走 stdin
async def send_command(container, command: str) -> str:
    try:
        return await rcon_client.send(command)
    except RCONError:
        # 降级到 docker exec
        exec_result = container.exec_run(f"/bin/bash -c 'echo {command}'")
        return exec_result.output.decode()
```

---

## 非功能性约束（NFR）提醒

PRD 要求 observer 守护进程**极低开销**：
- 稳态 CPU 占用 < 2%
- 内存占用 < 50MB

实现时的关键策略：
1. `events()` 是事件驱动，几乎零开销
2. `logs(stream=True)` 是阻塞 IO，不会消耗 CPU
3. `stats(decode=True, stream=True)` 每秒一条数据，开销极小
4. 正则匹配在 Python 中效率很高，200 行 deque 内存占用 < 100KB
5. 避免 `container.inspect()` / `container.reload()` 的高频轮询——用 `events()` 替代

---

## 实操步骤

当你开始实现 observer 某个功能时：

1. 确定子任务，找到上表对应的 API
2. 用 Read 工具阅读"你要读的文件"中列出的 docker-py 源码
3. 关注方法签名、参数含义、返回类型和流式读取模式
4. 基于 docker-py API 编写 Python 实现，注意线程安全和资源限制
5. 确保新代码与 `core/contracts/` 中的 `AnomalyEvent` 契约兼容
