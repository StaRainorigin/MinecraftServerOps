# MC-SRE 编码规范索引

> 本项目是 Minecraft 智能运维大脑，按"构建 → 感知 → 自愈 → 记忆"四大模块闭环组织。

---

## 包索引

| 包 | 状态 | 说明 |
|---|---|---|
| [builder/](./builder/index.md) | [开发中] | 服务端工作目录构建（多阶段异步流水线，多输入类型分支路由） |
| [core/](./core/index.md) | [开发中] | 跨模块共享内核（契约、路径、配置、事件） |
| [brain/](./brain/index.md) | [骨架] | AI 决策大脑与自愈闭环（LangGraph 图状态机） |
| [observer/](./observer/index.md) | [骨架] | 全天候可观测性与异常感知 |
| [memory/](./memory/index.md) | [骨架] | 系统记忆与自演进（RAG + ChatOps） |
| [infra/](./infra/index.md) | [骨架] | 外部依赖适配层（Docker / RCON / LLM / IM） |

---

## 跨包指南

| 指南 | 用途 |
|---|---|
| [Code Reuse Thinking Guide](./guides/code-reuse-thinking-guide.md) | 识别重复模式，减少不一致 bug |
| [Cross-Layer Thinking Guide](./guides/cross-layer-thinking-guide.md) | 跨层数据流思考，防止边界 bug |

---

## 全局约定

- **语言**：Spec 规则描述使用中文，代码片段和命令保持英文
- **契约先行**：模块间仅通过 `core/contracts/` 中的 Pydantic 模型通信，禁止裸 `dict`
- **路径单一来源**：所有持久化路径经 `core/paths.py` 统一管理
- **安全第一**：Zip Slip 防御、路径穿越拦截、EULA 严禁静默写入
- **依赖注入**：外部依赖（httpx client / EULA 闸）可注入替换，默认提供可跑实现
- **Emoji 限制**：代码中非必要不使用 emoji，如需图标商讨后引入图标库（如 Iconify / Font Awesome class）；Spec 文档中非必要不使用 emoji
- **Java 版本归属**：builder 声明需求（哪个版本），infra 负责探测/安装
- **可选 Mod 统一后缀**：未启用的可选 mod 使用 `.jar.disabled`，不删除
- **验证与修复分离**：构建后 smoke test 归 builder，诊断与自动修复归 brain
- **扩展点记录**：预留但暂不实现的功能，在对应 spec 中以 `[EXP-N]` 标记，记录位置、现状、扩展条件
