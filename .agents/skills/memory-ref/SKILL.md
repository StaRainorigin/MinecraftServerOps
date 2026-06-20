---
name: memory-ref
description: 编写 memory 模块（系统记忆与自演进）功能时自动加载的参考指南。当你需要实现 RAG 向量存储、相似度检索、经验写入/删除/降权、ChatOps 战报、RLHF 反馈等 memory/ 下任何功能时，务必先阅读本技能中的参考项目指引，从 ChromaDB 和 Swarms 中找到经过验证的 API 用法和设计模式再动手。
---

# Memory 模块参考指南

编写 `memory/` 模块功能时，核心依赖是 ChromaDB 的向量数据库 API。所有参考项目位于 `references/` 目录。

## 子系统速查表

| 子系统 | 子目录 | 你在写什么 | 核心参考项目 |
|--------|--------|-----------|-------------|
| RAG 记忆流水线 | `store/` + `rag/` | 特征清洗→向量化→KV 存储；故障时相似度检索 | ChromaDB |
| ChatOps 交互管道 | `chatops/` | 战报渲染 + RLHF 反馈 | Swarms（评估模式参考） |

---

## RAG 核心：ChromaDB 向量数据库

**你要读的文件：**

- `references/chroma/chromadb/__init__.py` — 客户端创建：PersistentClient / EphemeralClient / HttpClient
- `references/chroma/chromadb/api/models/Collection.py` — Collection 的 add / query / delete / update / upsert
- `references/chroma/chromadb/api/models/CollectionCommon.py` — 内部嵌入逻辑、输入校验
- `references/chroma/chromadb/api/types.py` — EmbeddingFunction 协议、Metadata 类型规则、Space 定义
- `references/chroma/chromadb/api/collection_configuration.py` — HNSW 配置（space / ef_construction / ef_search）

### 客户端初始化

```python
import chromadb

# 持久化模式（经验跨重启保留，PRD 必须使用）
client = chromadb.PersistentClient(path="./chroma_db")

# 上下文管理器（安全释放资源，特别是 SQLite 文件锁）
with chromadb.PersistentClient(path="./chroma_db") as client:
    # ... 使用 client ...
    pass
```

**不要使用** `EphemeralClient()`——数据仅存内存，重启丢失，违背"长期记忆"定位。

### 创建 Collection

```python
from chromadb.api.collection_configuration import CreateCollectionConfiguration, HnswConfiguration

# 必须使用 cosine 空间，因为 PRD 的相似度阈值（>= 0.95）基于余弦相似度
collection = client.get_or_create_collection(
    name="healing_experiences",
    configuration=CreateCollectionConfiguration(
        hnsw=HnswConfiguration(
            space="cosine",          # 关键！默认是 l2，无法直接映射到相似度阈值
            ef_construction=100,     # 构建时搜索宽度（越大越精确，越慢）
            ef_search=100,           # 查询时搜索宽度
            max_neighbors=16,        # HNSW 图最大连接数
        )
    ),
    metadata={"description": "MC-SRE 自愈经验向量库"},
)
```

### 写入经验（阶段一：特征清洗与记忆写入）

PRD 输入条件：Critic 评分 >= 85 才允许写入。

```python
def store_experience(
    collection,
    cleaned_log: str,       # 脱敏后的报错特征日志
    action_plan: ActionPlan, # 有效的修复指令
    critic_score: int,
):
    """将成功的自愈经验写入向量库。"""
    if critic_score < 85:
        return  # PRD: 评分不足，拒绝写入

    import uuid
    exp_id = uuid.uuid4().hex[:12]

    collection.add(
        ids=[exp_id],
        documents=[cleaned_log],        # 自动调用 embedding function
        metadatas=[{
            "action_plan_json": action_plan.model_dump_json(),
            "critic_score": critic_score,
            "weight": 1.0,               # 权重，用于降权而非删除
            "created_at": datetime.now().isoformat(),
            "last_hit": datetime.now().isoformat(),
            "hit_count": 0,
        }],
    )
```

### 日志脱敏清洗

PRD 要求：剔除时间戳、玩家 ID、实体坐标等"动态噪音"，只保留纯粹的 Java 堆栈异常签名。

```python
import re

def clean_log_for_embedding(raw_log: str) -> str:
    """脱敏清洗：只保留异常签名，去除动态噪音。"""
    # 移除时间戳 [HH:MM:SS]
    cleaned = re.sub(r'\[\d{2}:\d{2}:\d{2}\]', '', raw_log)
    # 移除玩家 ID（如 "Player123" / "Steve" 等游戏内名称）
    cleaned = re.sub(r'\b[A-Z][a-z]+[A-Z]\w*\b', '', cleaned)  # CamelCase 名称
    # 移除坐标 [x=123, y=64, z=-456]
    cleaned = re.sub(r'\[x=-?\d+\.?\d*,\s*y=-?\d+\.?\d*,\s*z=-?\d+\.?\d*\]', '', cleaned)
    # 移除线程名中的动态部分
    cleaned = re.sub(r'Server thread/\d+', 'Server thread/N', cleaned)
    # 保留 Java 异常签名（这是核心特征）
    # 如 java.lang.OutOfMemoryError, net.minecraft.crash.CrashReport
    return cleaned.strip()
```

### 相似度检索（阶段二：RAG 快速通道）

**关键发现：ChromaDB 的 `query()` 没有内置距离阈值参数！** 必须后处理过滤。

```python
def search_similar_experience(
    collection,
    error_signature: str,   # 脱敏后的报错特征
    similarity_threshold: float = 0.95,  # PRD 阈值
) -> dict | None:
    """在向量库中检索相似经验。命中则返回 ActionPlan，否则 None。"""

    results = collection.query(
        query_texts=[error_signature],
        n_results=10,            # 多取几个，后处理过滤
        include=["metadatas", "documents", "distances"],
        where={"weight": {"$gte": 0.5}},  # 过滤掉已降权的有毒记忆
    )

    if not results["ids"][0]:
        return None

    # cosine 空间下：distance = 1 - similarity
    # 所以 similarity >= 0.95 等价于 distance <= 0.05
    distance_threshold = 1.0 - similarity_threshold

    for id_, doc, dist, meta in zip(
        results["ids"][0],
        results["documents"][0],
        results["distances"][0],
        results["metadatas"][0],
    ):
        if dist <= distance_threshold:
            # 命中！更新 last_hit 和 hit_count
            collection.update(
                ids=[id_],
                metadatas=[{
                    **meta,
                    "last_hit": datetime.now().isoformat(),
                    "hit_count": meta.get("hit_count", 0) + 1,
                }],
            )
            # 返回对应的 ActionPlan
            plan_json = meta.get("action_plan_json", "{}")
            return ActionPlan.model_validate_json(plan_json)

    return None  # 无高相似度匹配，走 LLM 诊断通道
```

### 经验污染处理（PRD 边界情况）

PRD：RAG 命中但执行后仍崩 → 删除/降权该记忆，降级走 LLM 重新诊断。

```python
def poison_experience(collection, exp_id: str, hard_delete: bool = False):
    """标记经验为有毒——降权或删除。"""
    if hard_delete:
        collection.delete(ids=[exp_id])
    else:
        # 降权：将 weight 设为 0.1，后续查询会被 where 过滤掉
        meta = collection.get(ids=[exp_id], include=["metadatas"])["metadatas"][0]
        collection.update(
            ids=[exp_id],
            metadatas=[{**meta, "weight": 0.1, "poisoned": True}],
        )
```

### 存储溢出预防（PRD 边界情况）

PRD：LRU 淘汰 / TTL 清理，只保留高频核心经验。

ChromaDB 没有内置 TTL，需自行实现：

```python
def prune_stale_experiences(collection, max_age_days: int = 90, min_hit_count: int = 1):
    """清理过期和低频经验。"""
    cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()

    # 查找超过 max_age_days 未命中且命中次数低于阈值的记录
    stale = collection.get(
        where={
            "$and": [
                {"last_hit": {"$lt": cutoff}},
                {"hit_count": {"$lt": min_hit_count}},
            ]
        },
        include=["metadatas"],
    )

    if stale["ids"]:
        collection.delete(ids=stale["ids"])
        return len(stale["ids"])
    return 0
```

### Metadata 过滤语法

ChromaDB 的 `where` 参数支持丰富的过滤语法，在记忆管理中非常有用：

```python
# 等值过滤
where = {"poisoned": False}

# 范围过滤
where = {"critic_score": {"$gte": 85}}

# 逻辑组合
where = {"$and": [
    {"weight": {"$gte": 0.5}},
    {"poisoned": {"$ne": True}},
]}

# 文档内容过滤
where_document = {"$contains": "OutOfMemoryError"}
```

可用操作符：`$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`, `$contains`, `$not_contains`

---

## ChatOps 战报与 RLHF

**你要读的文件：**

- `references/swarms/swarms/agents/agent_judge.py` — Judge Agent 的评分模式（reward score 0/1）
- `references/swarms/swarms/structs/debate_with_judge.py` — 辩论+评判模式（可参考战报中的"故障方"vs"修复方"对比）

### 战报模板（PRD 要求）

```python
POST_MORTEM_TEMPLATE = """# 🔧 MC-SRE 自愈战报

## 基本信息
- **宕机时间**: {downtime}
- **恢复耗时 (MTTR)**: {mttr}
- **故障类型**: {fault_type}

## 故障根因摘要
{root_cause}

## 执行动作列表
{action_list}

## 当前系统状态
- **TPS**: {current_tps}
- **内存使用率**: {current_mem_percent}%
- **模组状态**: {mod_status}

---
[👍 修得好]  [👎 乱修，回滚！]
"""
```

### RLHF 反馈处理

PRD：用户点击 👎 → 立即执行历史快照回滚，并在向量库中将该条记忆标记为"有毒"。

```python
def handle_rlhf_feedback(
    collection,
    experience_id: str,
    feedback: Literal["thumbs_up", "thumbs_down"],
    instance_root: Path,
    snapshot_id: str,
):
    """处理用户的 RLHF 反馈。"""
    if feedback == "thumbs_down":
        # 1. 立即回滚到快照
        rollback_to_snapshot(snapshot_id, instance_root)
        # 2. 标记记忆为有毒
        poison_experience(collection, experience_id, hard_delete=False)
        # 3. 通知下游
        return "已回滚并标记有毒记忆"
    else:
        # 正面反馈：提升权重
        meta = collection.get(ids=[experience_id], include=["metadatas"])["metadatas"][0]
        collection.update(
            ids=[experience_id],
            metadatas=[{
                **meta,
                "weight": min(meta.get("weight", 1.0) + 0.1, 2.0),
                "rlhf_positive": meta.get("rlhf_positive", 0) + 1,
            }],
        )
        return "已增强记忆权重"
```

---

## RAG 快速通道性能约束（NFR）

PRD 要求：RAG 检索耗时 < 200ms（对比 LLM 推理 10s-30s）。

性能优化策略：
1. **cosine 空间 + HNSW 索引**：ChromaDB 的 HNSW 算法在 cosine 空间下的检索延迟在万级数据量时通常 < 10ms
2. **ef_search 参数调优**：默认 100，可降低到 50 换取更快查询（牺牲少量精度）
3. **预计算 Embedding**：故障发生时先调用本地轻量模型（如 BGE-small）生成向量，再直接用 `query_embeddings` 而非 `query_texts` 传入，跳过 ChromaDB 的嵌入步骤
4. **PersistentClient 的 SQLite 索引**：磁盘持久化的查询性能与内存模式接近

```python
# 高性能查询模式：预计算 embedding
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

ef = SentenceTransformerEmbeddingFunction(model_name="BAAI/bge-small-en-v1.5")

# 预计算查询向量
query_embedding = ef([error_signature])

# 直接用向量查询，跳过 ChromaDB 内部嵌入
results = collection.query(
    query_embeddings=query_embedding,
    n_results=5,
    include=["metadatas", "distances"],
)
```

---

## Embedding 模型选择

ChromaDB 支持多种 Embedding 模型（`references/chroma/chromadb/utils/embedding_functions/`）：

| 模型 | 维度 | 适用场景 |
|------|------|---------|
| all-MiniLM-L6-v2（默认） | 384 | 通用英文，速度快 |
| BAAI/bge-small-en-v1.5 | 384 | 英文语义搜索，性能优于默认 |
| text-embedding-3-small (OpenAI) | 1536 | 高质量，需 API Key |
| Ollama 本地模型 | 可变 | 离线场景，需部署 Ollama |

推荐使用 **BGE-small** 作为默认模型：本地运行、无需 API Key、384 维向量节省存储、中文 Java 堆栈日志表现良好。

---

## 实操步骤

当你开始实现 memory 某个功能时：

1. 确定子系统（RAG 管道 vs ChatOps），找到上表对应的 API
2. 用 Read 工具阅读"你要读的文件"中列出的 ChromaDB 源码
3. 重点阅读 `Collection.py` 的 add / query / delete / update 方法签名
4. 记住：query() 没有距离阈值参数，必须后处理过滤
5. 记住：必须使用 cosine 空间，否则无法映射到 PRD 的 0.95 相似度阈值
6. 确保新代码与 `core/contracts/` 中的数据契约兼容
7. 确保经验写入前检查 Critic 评分 >= 85
8. 确保经验污染时同时处理降权和 LLM 降级两条路径
