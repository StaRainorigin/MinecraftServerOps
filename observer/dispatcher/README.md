# `observer/dispatcher/` · 阶段四：事件防抖与唤醒

将崩溃瞬间喷发的大量报错合并为单一事件，组装结构化 `AnomalyEvent` 并唤醒下游 LangGraph 状态机。

## 文件职责

| 文件 | 职责 |
|------|------|
| `anomaly_emitter.py` | **节流防抖**：5 秒窗口期内合并所有报错为单一 `AnomalyEvent`；组装【时间戳】+【触发原因】+【资源利用率】+【200 行上下文日志】为 JSON Payload |

## 关键约束

- **5 秒防抖窗口**：服务器崩溃 1 秒内喷发大量 `FATAL` 日志，必须聚合为单一事件，避免风暴式唤醒 brain。

## 上游/下游

- 上游：`watchdog/`（硬宕机）、`logstream/`（200 行上下文）、`metrics/`（软宕机）
- 下游：`core/events.py` 事件总线 → brain 模块
