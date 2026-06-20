# `memory/store/` · 阶段一：特征清洗与记忆写入

接收成功修复的上下文，脱敏清洗后向量化嵌入，与有效 `ActionPlan` 绑定写入本地向量库。

## 文件职责

| 文件 | 职责 |
|------|------|
| `cleanser.py` | **日志脱敏清洗**：剔除时间戳、玩家 ID、实体坐标等动态噪音，只保留纯 Java 堆栈异常签名（Exception Signature） |
| `embedder.py` | 调用轻量级 Embedding 模型（`BGE-small` / `text-embedding-3-small`）转化为多维向量 |
| `vector_db.py` | 本地轻量级向量库客户端封装（ChromaDB / Qdrant）；以【向量】为 Key、【`ActionPlan` JSON】为 Value 绑定存储 |
| `retention.py` | **存储溢出预防**：LRU（最近最少使用）淘汰或定期 TTL 清理，只保留高频核心经验 |

## 写入门槛

- 仅当 verify 判定**成功修复**且 Critic 评分 `>= 85` 时才允许写入，防低质经验污染。
