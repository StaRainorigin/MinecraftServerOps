# core 模块编码规范

> 跨模块共享内核：契约、路径常量、配置、事件总线、顶层编排

---

## 开发前检查清单

- [ ] 新增的跨模块数据结构是否在 `core/contracts/` 中定义为 Pydantic 模型
- [ ] 新增的持久化路径是否在 `core/paths.py` 中定义
- [ ] 新增的配置项是否在 `core/config.py` 的 `Settings` 中定义并支持环境变量
- [ ] 是否有循环导入风险（core 不应依赖 builder/brain/observer/memory）

---

## 质量检查

- [ ] `core/` 下无业务逻辑（仅契约、路径、配置、编排桩）
- [ ] 无循环导入（core 是最底层包，不应 import 上层模块）
- [ ] Pydantic 模型使用 `Field(default_factory=list)` 而非 `Field(default=[])`

---

## 规范索引

| 规范 | 说明 |
|---|---|
| [契约定义](./contracts.md) | Pydantic 模型定义规范 |
| [路径管理](./paths.md) | 路径常量与派生函数 |
| [配置系统](./config.md) | Settings dataclass 与环境变量 |

---

## 关键文件速查

| 文件 | 职责 |
|---|---|
| `core/contracts/manifest.py` | Manifest / ModEntry / LoaderType / ModSource |
| `core/contracts/build_results.py` | BuildResult / InputMode / EulaDecision / DownloadReport 等 |
| `core/paths.py` | SERVER_POOL / SANDBOX_ROOT / SNAPSHOT_ROOT / DOWNLOAD_CACHE + 派生函数 |
| `core/config.py` | Settings dataclass + 环境变量 + .env 加载 + 全局单例 `settings` |
| `core/events.py` | 事件总线（TODO） |
| `core/orchestrator.py` | 顶层编排（TODO） |
