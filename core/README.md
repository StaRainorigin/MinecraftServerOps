# `core/` · 跨模块共享内核

本目录承载四大模块共用的基础设施：数据契约、配置、路径常量、事件总线，以及把它们串成完整闭环的顶层编排入口。

## 职责

| 文件 | 职责 | 上下游关系 |
|------|------|-----------|
| `config.py` | 全局配置加载（LLM / Docker / 向量库 / 阈值参数等） | 被所有模块读取 |
| `paths.py` | 实例根目录、快照隔离区、`server_pool/instance_*`、临时沙箱等路径常量 | builder / brain / memory 共用 |
| `events.py` | 事件总线与 `AnomalyEvent` 派发（observer → brain 的传输契约） | observer 产生，brain 消费 |
| `orchestrator.py` | 顶层编排入口：串联四大模块的总调度 | 对接 CLI / API / 机器人 |
| `contracts/` | 跨模块数据契约（Pydantic 模型，后续填充） | 见子目录 README |

## 设计原则

- **契约先行**：模块间仅通过 `contracts/` 中的结构化对象通信，禁止跨模块直接 import 实现细节。
- **路径单一来源**：所有持久化路径（实例目录、快照区、交付池）必须经 `paths.py` 统一管理，便于实例隔离与安全沙箱校验（`brain/sandbox/`）。
