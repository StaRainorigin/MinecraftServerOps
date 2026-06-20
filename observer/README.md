# `observer/` · 【模块二】全天候可观测性与异常感知

MC-SRE 系统的"眼睛与耳朵"（数据感知层），运行在服务端的低开销守护进程。将人工盯盘的日志流和性能指标转化为 24 小时无人值守自动化监控，在崩溃/内存溢出/严重卡顿时精准截取"犯罪现场"上下文，组装成结构化事件唤醒 LangGraph 大脑。

## 4 个并发子任务

| 阶段 | 子目录 | 职责 |
|------|--------|------|
| 一 | `watchdog/` | 生命周期看门狗（容器 Exited / OOMKilled → 硬宕机事件） |
| 二 | `logstream/` | 日志流滑动窗口捕获（正则清洗 + 200 行 Ring Buffer 上下文冻结） |
| 三 | `metrics/` | 业务水位巡检（CPU/内存采样 + TPS 嗅探 → 软宕机事件） |
| 四 | `dispatcher/` | 事件防抖与唤醒（5 秒窗口聚合 + 组装 AnomalyEvent 唤醒 LangGraph） |

## 入口

- `daemon.py`：守护进程主循环，并发调度上述 4 个子任务。

## 输入输出

- **输入**：①Docker stdout/stderr 实时日志流 ②Cgroups 硬件资源（CPU/内存）③游戏内 TPS 指标
- **输出**：标准 JSON 格式 `AnomalyEvent`，通过 HTTP POST 或内部消息队列推送给 LangGraph 控制面（`core/events.py`）

## 非功能性约束（NFR）

- **极低开销**：与游戏服务端同机运行，稳态 CPU 占用 `< 2%`，内存占用 `< 50MB`，绝不拖垮服务器。

## 边界情况

- **日志风暴**：限速阀截断丢弃，标记 `LOG_SPAM_DETECTED`（见 `logstream/rate_limiter.py`）
- **静默崩溃**：RCON 连续 3 次超时无响应，无视日志状态强制触发异常（见 `metrics/tps_probe.py`）
