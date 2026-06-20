# `core/contracts/` · 跨模块数据契约

本目录集中定义四大模块之间流转的结构化数据契约。所有模块间通信必须使用此处的类型，确保接口先于实现冻结。

## 核心契约（待填充）

| 契约 | 用途 | 生产者 → 消费者 |
|------|------|----------------|
| `AnomalyEvent` | 异常感知事件负载（触发类型 + 资源指标 + 200 行上下文日志） | observer → brain |
| `ActionPlan` | 结构化修复动作序列（LLM 强约束输出，Pydantic 校验） | brain（诊断）→ brain（执行） |
| `Manifest` | 整合包元数据（版本 / 加载器 / ProjectID-FileID 映射） | builder（解包）→ builder（下载） |
| `SnapshotRef` | 事务性快照引用（快照路径 + 创建时间 + 校验和） | brain（snapshot）→ brain（rollback） |
| `MemoryRecord` | RAG 记忆记录（向量 + ActionPlan + 健康度评分） | brain（verify）→ memory（store） |
| `PostMortem` | 事故复盘战报（宕机时间 / MTTR / 根因 / 动作列表） | brain / memory → chatops |

## 设计约束（来自 PRD）

- **禁止裸 dict 流转**：模块边界一律使用 Pydantic 模型，附带字段校验与默认值。
- **ActionPlan 动作枚举锁定**：仅允许 `MODIFY_JVM_ARGS` / `DISABLE_COMPONENT` / `UPDATE_CONFIG` 等白名单动作（详见 `brain/actions/`）。
- **AnomalyEvent 上下文冻结**：必须携带报错前 100 行 + 后 100 行的完整堆栈，禁止裁剪。
