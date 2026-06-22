# builder 模块编码规范

> 模块一：服务端工作目录构建 (Server Workspace Builder)
> 将多种用户输入源（引导包 / 完整客户端）全自动编译为开箱即用的服务端工作目录。

---

## 开发前检查清单

- [ ] 确认修改的阶段编号（①unpack ②metadata ③fetcher ④merge ⑤install ⑥deliver）
- [ ] 新增的 Pydantic 模型是否在 `core/contracts/` 中定义
- [ ] 涉及文件 I/O 的路径是否经 `core/paths.py` 派生
- [ ] 异步函数是否正确使用 `async def` + `await`（pipeline 主体为 async）
- [ ] 异常是否继承 `BuildError` 基类
- [ ] 降级路径是否有日志记录

---

## 质量检查

- [ ] 无裸 `dict` 在模块间传递（必须用 Pydantic 模型）
- [ ] 无硬编码绝对路径（必须经 `core/paths.py`）
- [ ] 无静默写入 `eula=true`（必须经 `EulaGate` 协议）
- [ ] 新增下载源已在 `sources.py` 中注册并设置优先级
- [ ] 黑名单关键字已加到 `blacklist.py` 并考虑 NeoForge 服务端兼容性

---

## 规范索引

| 规范 | 说明 |
|---|---|
| [流水线架构](./pipeline.md) | 六阶段异步流水线总调度 |
| [数据契约](./contracts.md) | Pydantic 模型定义与跨阶段流转 |
| [下载引擎](./fetcher.md) | 多源下载、引擎切换、重试策略 |
| [异常处理](./error-handling.md) | 异常层级、熔断机制、降级策略 |
| [目录结构](./directory-structure.md) | 模块内文件组织 |

---

## 关键文件速查

| 文件 | 职责 |
|---|---|
| `builder/pipeline.py` | 流水线总调度（`build_workspace` 入口） |
| `builder/__main__.py` | CLI 入口（`python -m builder`） |
| `builder/errors.py` | 异常类型层级 |
| `builder/fetcher/__init__.py` | 引擎路由（`get_fetcher`） |
| `builder/fetcher/downloader.py` | aria2c 主力引擎 |
| `builder/fetcher/downloader_httpx.py` | httpx 备用引擎 |
| `builder/fetcher/sources.py` | URL 构造层（源定义 + 优先级） |
| `builder/fetcher/cf_resolver.py` | CurseForge 文件名解析 |
| `builder/merge/blacklist.py` | 纯客户端 Mod 黑名单 |
| `builder/merge/eula_gate.py` | EULA 交互闸（Protocol + 默认实现） |
