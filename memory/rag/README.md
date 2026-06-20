# `memory/rag/` · 阶段二：故障前置拦截（RAG 快速通道）

**改变诊断工作流**：发生崩溃后不再第一时间请求大模型，优先去本地向量库做余弦相似度检索，命中即跳过 LLM 秒级短路修复。

## 文件职责

| 文件 | 职责 |
|------|------|
| `fast_path.py` | **短路执行**：相似度 `>= 0.95` 直接提取历史 `ActionPlan` 送沙箱执行（"肌肉记忆"）；`< 0.95` 降级走 brain 的 LLM 缓慢推理 |
| `similarity.py` | 余弦相似度（Cosine Similarity）计算 + 阈值判定 |

## 关键约束

- **性能 NFR**：快速通道检索耗时必须 `< 200ms`，凸显相对 LLM 推理（10s-30s）的绝对优势。
- **经验污染兜底**：若 RAG 命中但执行后仍崩，说明历史经验不适用新环境 → 删除/降权该记忆 + 强制降级走 LLM 重新诊断（见 `store/vector_db.py`）。

## 上游/下游

- 上游：observer 的 `AnomalyEvent`（经编排层路由优先进入本通道）
- 下游：命中 → `brain/nodes/execute.py`（跳过 diagnose）；未命中 → `brain/nodes/diagnose.py`
