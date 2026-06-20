# `builder/fetcher/` · 阶段三：云端多源依赖解析与下载

借鉴 PCL / HMCL 的多源下载架构，放弃单一依赖 CurseForge 官方 API（防国内封锁与限流）。实现多下载源动态轮询、并发下载、单文件失败自动切换镜像源重试。

## 文件职责

| 文件 | 职责 |
|------|------|
| `sources.py` | 下载源定义与优先级：①官方源（Mojang/CurseForge/Modrinth）②国内镜像（BMCLAPI、MCBBS 镜像等） |
| `downloader.py` | 多线程并发下载；单文件失败自动切换至镜像源重试 |
| `missing_log.py` | **全网断流降级**：某 Mod 在所有源都不可用时跳过，记录到 `missing_mods.log`，交付时提醒服主手动补全 |

## 关键策略

- **多源轮询**：同时或按优先级轮询官方源 + 国内镜像源，缓解网络封锁与 API 限流。
- **并发容错**：多线程并发下载，单文件失败自动切换镜像重试，不因单点失败拖垮整批。
- **断流降级**：所有镜像都无法获取（历史下架/删档）时跳过该 Mod，写入 `missing_mods.log`，严禁卡死流水线。

## 上游/下游

- 上游：`metadata/` 提供 `Manifest`（版本 / 加载器 / ProjectID-FileID 映射）
- 下游：`merge/` 接收下载完成的 .jar 与核心文件
