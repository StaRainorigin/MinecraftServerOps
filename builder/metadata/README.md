# `builder/metadata/` · 阶段二：元数据提取（仅限引导包模式）

读取引导包的标准索引 JSON，提取并固化后续下载引擎所需的关键数据。

> ⚠️ 本阶段**仅引导包模式**触发；完整客户端模式跳过此阶段。

## 提取内容

- 游戏核心版本（如 `1.20.1`）
- 加载器类型及版本（如 `Forge 47.1.3` / `Fabric 0.14.22`）
- 模组 ProjectID 与 FileID 映射表

## 文件职责

| 文件 | 职责 |
|------|------|
| `curseforge.py` | 解析 `manifest.json`（CurseForge 规范） |
| `modrinth.py` | 解析 `modrinth.index.json`（Modrinth 规范） |
| `schema.py` | 元数据结构定义，输出统一的 `Manifest` 契约（见 `core/contracts/`） |

## 上游/下游

- 上游：`unpack/discriminator.py` 判定为引导包模式后调用
- 下游：`fetcher/` 接收 `Manifest` 进行多源下载
