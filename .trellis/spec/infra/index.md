# infra 模块编码规范

> 外部依赖适配层：Docker / RCON / LLM / IM 平台
> 状态：[骨架] 阶段（仅占位 docstring）

---

## 当前状态

所有文件均为占位骨架，仅包含模块 docstring，逻辑待后续填充。

---

## 设计规划

根据 PRD，infra 模块应实现：

- **Docker 适配**：`docker_client.py` — 容器生命周期/状态查询/logs(stream)/Cgroups 资源
- **RCON 适配**：`rcon_client.py` — 远程控制台命令执行
- **LLM 适配**：`llm_client.py` — 诊断推理/Critic 打分/Embedding 向量化
- **IM 平台适配**：`chatops_adapters/` — 钉钉/qq/discord

---

## 预期文件结构

```
infra/
├── docker_client.py
├── rcon_client.py
├── llm_client.py
└── chatops_adapters/
    ├── dingtalk.py
    ├── qq.py
    └── discord.py
```

---

## 实现前的注意事项

- infra 是适配层，不应包含业务逻辑，仅封装外部 API 调用
- 所有外部调用必须有超时和重试机制
- 凭证通过 `core/config.py` 的 `Settings` 管理，不在代码中硬编码
- 每个适配器应定义 Protocol 接口，支持 mock 测试
