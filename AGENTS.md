# MC-SRE 项目全局指令

## 核心原则：编码前先查参考

本项目在 `references/` 目录下克隆了 11 个经过验证的开源项目，作为实现参考。**在编写任何功能前，必须先查阅对应参考项目中的相关实现，将经过验证的模式适配为 Python 代码。** 不要从零设计——这些项目已经解决了你即将遇到的问题。

## 模块→参考项目映射表

编写某个模块功能时，**先读对应参考文件**：

| 你在写的模块 | 必须查阅的参考项目 | 关键文件位置 |
|------------|------------------|------------|
| **builder/fetcher/** 多源下载 | PCL2 + HMCL | `references/PCL2/Plain Craft Launcher 2/Modules/Minecraft/ModDownload.vb`（URL重写表、源竞争回退）· `references/PCL2/Plain Craft Launcher 2/Modules/Base/ModNet.vb`（限速、源失败检测、IP可靠性）· `references/HMCL/HMCLCore/src/main/java/org/jackhuang/hmcl/download/DownloadProvider.java`（接口抽象）· `references/HMCL/HMCLCore/src/main/java/org/jackhuang/hmcl/download/BMCLAPIDownloadProvider.java`（候选URL逻辑）· `references/HMCL/HMCLCore/src/main/java/org/jackhuang/hmcl/download/AutoDownloadProvider.java`（组合Provider） |
| **builder/metadata/** 清单解析 | packwiz | `references/packwiz/cmd/curseforge.go`（CF manifest解析）· `references/packwiz/cmd/modrinth.go`（Modrinth index解析）· `references/packwiz/core/mod.go`（哈希校验） |
| **builder/merge/** 客户端清洗+EULA | docker-minecraft-server | `references/docker-minecraft-server/files/cf-exclude-include.json`（170+客户端Mod排除列表）· `references/docker-minecraft-server/files/modrinth-exclude-include.json`· `references/docker-minecraft-server/scripts/start-configuration`（EULA前置检查） |
| **builder/unpack/** 解包判别 | docker-minecraft-server | `references/docker-minecraft-server/scripts/start-deployAutoCF`· `references/docker-minecraft-server/scripts/start-deployModrinth` |
| **observer/watchdog/** 生命周期看门狗 | docker-py | `references/docker-py/docker/api/daemon.py`（events方法）· `references/docker-py/docker/models/containers.py`（status/health属性） |
| **observer/logstream/** 日志流窗口 | docker-py | `references/docker-py/docker/api/container.py`（logs方法，line 821）· `references/docker-py/docker/types/daemon.py`（CancellableStream） |
| **observer/metrics/** 水位巡检 | docker-py | `references/docker-py/docker/api/container.py`（stats方法，line 1139）· `references/docker-py/tests/unit/fake_stat.py`（Stats数据结构） |
| **observer/** RCON命令 | mc-server-runner | `references/mc-server-runner/main.go`（sendCommand双路径：RCON优先stdin兜底） |
| **brain/graph.py** 图状态机 | LangGraph | `references/langgraph/libs/langgraph/langgraph/graph/state.py`（StateGraph API）· `references/langgraph/libs/langgraph/langgraph/types.py`（RetryPolicy/Command） |
| **brain/nodes/snapshot.py** 快照 | LangGraph | `references/langgraph/libs/checkpoint/langgraph/checkpoint/base/__init__.py`（BaseCheckpointSaver）· `references/langgraph/libs/checkpoint/langgraph/checkpoint/memory/__init__.py`（InMemorySaver） |
| **brain/nodes/diagnose.py** LLM诊断 | LangChain | `references/langchain/libs/core/langchain_core/output_parsers/pydantic.py`（PydanticOutputParser）· `references/langchain/libs/core/langchain_core/language_models/chat_models.py`（with_structured_output，line 2357） |
| **brain/nodes/critique.py** Critic评估 | Swarms | `references/swarms/swarms/structs/council_as_judge.py`（多维度并行评估）· `references/swarms/swarms/structs/debate_with_judge.py`· `references/swarms/swarms/agents/flexion_agent.py`（Reflexion反思循环） |
| **memory/store/** 经验写入 | ChromaDB | `references/chroma/chromadb/api/models/Collection.py`（add/query/delete/update）· `references/chroma/chromadb/__init__.py`（PersistentClient） |
| **memory/rag/** 相似度检索 | ChromaDB | 同上。**关键：query()无内置距离阈值，必须后处理；必须用cosine空间** |

## 已知的实现差距（优先修复）

1. **`builder/fetcher/sources.py`**：BMCLAPI URL 映射不完整，缺少 `libraries`、`maven`、`fabric-meta` 路径和 MCIMirror 备用镜像 → 参考 PCL2 ModDownload.vb 1246-1310 行的完整重写表
2. **`builder/merge/blacklist.py`**：黑名单仅 ~60 条硬编码关键字 → 参考 docker-minecraft-server 的 cf-exclude-include.json（170+ 条）迁移为 JSON 配置 + forceIncludes 机制
3. **`builder/fetcher/downloader.py`**：下载后无哈希校验 → 参考 packwiz 的 teeHashes 模式
4. **`brain/graph.py` + `state.py`**：仍是空壳 → 基于 LangGraph StateGraph API 构建 5 节点状态机
5. **`observer/daemon.py`**：仍是空壳 → 基于 docker-py 的 events/logs/stats 三线程架构

## 工作模式

**执行任何编码任务时，调用 `/dev-loop` 进入自主开发循环。** 该 skill 驱动你自主规划→拆解→并行探索→编码→测试→修复，循环推进直到任务完成，无需用户逐步指令。

## 详细参考指南

每个模块有独立的 skill 文件，包含完整的 API 用法、代码模板和边界情况处理：

- `/builder-ref` — builder 模块完整参考（多源下载、清单解析、客户端清洗、EULA）
- `/observer-ref` — observer 模块完整参考（看门狗、日志窗口、水位巡检、事件防抖）
- `/brain-ref` — brain 模块完整参考（图状态机、LLM强约束输出、Critic评估、快照回滚）
- `/memory-ref` — memory 模块完整参考（ChromaDB向量库、RAG检索、经验污染、RLHF）

**当你需要实现某个具体功能时，调用对应的 skill 获取详细指引。**
