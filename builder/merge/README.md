# `builder/merge/` · 阶段四：资产合并与配置组装

对下载完成（模式 A）或本地扫描（模式 B）的资产进行服务端清洗、配置归并，并通过 EULA 交互闸放行。

## 文件职责

| 文件 | 职责 |
|------|------|
| `client_cleaner.py` | **服务端清洗（仅模式 B 客户端）**：扫描 `mods/`，将纯客户端 Mod 改后缀 `.disabled` 或剔除，防服务端加载客户端渲染类崩溃 |
| `blacklist.py` | 纯客户端 Mod 黑名单维护：`Optifine`、`Sodium`、`Iris`、`Xaero's Minimap`、`SmoothBoot` 等 |
| `config_merger.py` | 将解压出的 `config/`、`defaultconfigs/`、`kubejs/` 等自定义脚本全量归并复制到最终工作目录 |
| `eula_gate.py` | **Human-in-the-loop EULA 闸**：向前端/机器人/控制台透出 EULA 文本，仅当用户点击"我同意"后写 `eula=true` 并放行 |

## 关键边界

- **严禁静默生成已同意的 eula.txt**：必须显式交互确认，未确认不得写入。
- **EULA 拒绝熔断**：用户点"我拒绝"或超时（5 分钟）未确认 → 立即终止流水线，撤销所有操作，返回终止提示。
- **客户端黑名单剔除**：纯客户端美化/优化/辅助模组必须剥离，避免服务端崩溃。

## 上游/下游

- 上游：`fetcher/`（模式 A 下载产物）或 `unpack/`（模式 B 直接进入清洗）
- 下游：`deliver/` 进行完整性校验与交付
