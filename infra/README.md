# `infra/` · 外部依赖适配层

四大模块与外部世界（Docker 引擎、游戏 RCON、LLM 服务、IM 平台）交互的薄封装。集中隔离外部 SDK 细节，上层模块只面向稳定接口编程，便于替换实现与 mock 测试。

## 文件职责

| 文件 | 职责 | 主要消费方 |
|------|------|-----------|
| `docker_client.py` | Docker Daemon 访问：容器生命周期（启停/重启）、状态查询（ExitCode/OOMKilled）、`logs(stream=True)` 流式日志、Cgroups 资源读取 | observer（watchdog/logstream/metrics）、brain（verify 重启） |
| `rcon_client.py` | RCON 协议封装：发送 `tps` 指令、心跳探活、超时检测（静默崩溃兜底） | observer（metrics/tps_probe） |
| `llm_client.py` | LLM 调用封装：诊断大脑推理、Critic 打分、Embedding 向量化 | brain（diagnose/critique）、memory（store/embedder） |
| `chatops_adapters/` | 各 IM 平台适配器（Discord / QQ / 钉钉） | memory（chatops/notifier） |

## 设计原则

- **适配器模式**：每类外部依赖一个 client，屏蔽 SDK 差异。
- **接口稳定**：上层不直接依赖 SDK，更换实现（如 ChromaDB 换 Qdrant、Discord 换飞书）只改本层。
- **可 mock**：所有 client 面向接口，便于测试注入。
