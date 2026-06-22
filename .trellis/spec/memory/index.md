# memory 模块编码规范

> 模块四：系统记忆与自演进（RAG + ChatOps）
> 状态：[骨架] 阶段（仅占位 docstring）

---

## 当前状态

所有文件均为占位骨架，仅包含模块 docstring，逻辑待后续填充。

---

## 设计规划

根据 PRD，memory 模块应实现：

- **RAG 向量存储**：`store/vector_db.py` + `embedder.py` + `similarity.py` + `fast_path.py`
- **经验管理**：`store/retention.py`（降权/过期）+ `cleanser.py`（清洗）
- **ChatOps 通知**：`chatops/notifier.py` + `feedback.py`（RLHF）+ `postmortem.py`

---

## 预期文件结构

```
memory/
├── store/
│   ├── vector_db.py
│   ├── embedder.py
│   ├── similarity.py
│   ├── fast_path.py
│   ├── retention.py
│   └── cleanser.py
├── rag/
│   ├── similarity.py
│   └── fast_path.py
└── chatops/
    ├── notifier.py
    ├── feedback.py
    └── postmortem.py
```

---

## 实现前的注意事项

- 实现前先加载 `/memory-ref` 技能，参考 ChromaDB 和 Swarms 的 API 用法
- 向量存储使用本地 ChromaDB，数据不入版本控制（`.gitignore` 中已排除 `chroma_data/`）
- 经验写入需要人工确认或 RLHF 反馈，避免错误经验污染知识库
- 命中记忆时走 `fast_path` 秒级短路修复，无需经过完整 brain 图
