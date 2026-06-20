---
name: builder-ref
description: 编写 builder 模块（服务端工作目录构建）功能时自动加载的参考指南。当你需要实现多源下载、整合包解析、客户端 Mod 清洗、EULA 处理、ZIP 解包判别等 builder/ 下任何功能时，务必先阅读本技能中的参考项目指引，从 PCL2/HMCL/packwiz/docker-minecraft-server 等开源项目中找到经过验证的设计模式再动手。
---

# Builder 模块参考指南

编写 `builder/` 模块功能时，先确定你正在处理的子阶段，然后阅读对应参考项目中的关键文件。所有参考项目位于 `references/` 目录。

## 阶段速查表

| 阶段 | 子目录 | 你在写什么 | 去读哪个参考项目 |
|------|--------|-----------|----------------|
| 一 | `unpack/` | ZIP 安全解压、根目录定位、模式判别 | docker-minecraft-server |
| 二 | `metadata/` | CurseForge/Modrinth 清单解析 | packwiz |
| 三 | `fetcher/` | 多源下载、镜像切换、并发限速 | PCL2、HMCL |
| 四 | `merge/` | 客户端 Mod 清洗、EULA 闸 | docker-minecraft-server |
| 五 | `deliver/` | 完整性校验、目录交付 | mc-server-runner |

---

## 阶段一：解包与判别 → 读 docker-minecraft-server

**你要读的文件：**

- `references/docker-minecraft-server/scripts/start-deployAutoCF` — Auto CurseForge 部署脚本，展示了如何通过环境变量识别整合包类型（CF_PAGE_URL / CF_SLUG / CF_FILE_ID）
- `references/docker-minecraft-server/scripts/start-deployModrinth` — Modrinth 部署脚本，展示 MODRINTH_MODPACK 参数解析
- `references/docker-minecraft-server/scripts/start-deployCF` — 旧版 CF 部署，展示如何处理嵌套文件夹（FTB_BASE_DIR）和 start 脚本查找

**关键参考模式：**

1. **嵌套文件夹自适应**：docker-minecraft-server 在解压后查找多种 start 脚本名（ServerStart.sh, start-server.sh, run.sh），这暗示整合包可能有多层嵌套。我们的 `unpack/root_locator.py` 已有深度优先搜索，但应考虑更激进的探查策略。

2. **MODPACK_PLATFORM 判别**：`start-configuration` 脚本通过 `MODPACK_PLATFORM` 环境变量分流到不同部署脚本，类似于我们的 A/B 模式判别。

---

## 阶段二：引导包解析 → 读 packwiz

**你要读的文件：**

- `references/packwiz/cmd/curseforge.go` — CurseForge manifest.json 的完整解析逻辑
- `references/packwiz/cmd/modrinth.go` — Modrinth index.json 的完整解析逻辑
- `references/packwiz/core/index.go` — packwiz 自身索引文件格式
- `references/packwiz/core/mod.go` — Mod 数据结构和哈希校验

**关键参考模式：**

1. **格式判别**：packwiz 不只看文件名，还检查 JSON 字段（CurseForge 的 `manifestType` 字段）。我们的 `discriminator.py` 已有 `_is_bootstrap_manifest()` 做类似检查，可参考 packwiz 的完整判别逻辑。

2. **teeHashes 同时下载+校验**：packwiz 在下载流中同时计算 SHA1/SHA256，下载完成即校验，无需二次读取文件。我们现有 `downloader.py` 下载后没有哈希校验——这是一个必须补上的缺陷。

3. **metadata:curseforge 延迟解析**：packwiz 对 CF 模组支持"仅存 projectID/fileID，下载时再查 API 获取真实 URL"。这可以缓解 CF API 限流问题。

4. **缓存索引**：packwiz 的缓存按 sha256 建立列式索引，下载前先查缓存，可避免重复下载。我们的 `DOWNLOAD_CACHE` 目录（`core/paths.py`）尚未实现缓存查询逻辑。

---

## 阶段三：多源下载 → 读 PCL2 和 HMCL

这是最复杂的阶段，两个参考项目各有侧重。

### PCL2：下载引擎的硬核实现

**你要读的文件：**

- `references/PCL2/Plain Craft Launcher 2/Modules/Minecraft/ModDownload.vb` — 镜像源定义、DlSourceLoader 竞争回退、DlSourceOrder 源优先级、URL 重写表（1246-1310 行）
- `references/PCL2/Plain Craft Launcher 2/Modules/Base/ModNet.vb` — 核心下载引擎：NetFile/NetSource/NetThread 类、NetManager 调度器、限速逻辑、源失败检测、IP 可靠性追踪

**关键参考模式：**

1. **竞争式源回退（DlSourceLoader）**：不是简单的"失败换下一个"，而是"先启动镜像源，30s 内没完成则并行启动官方源，谁先完成用谁"。对版本清单等元数据下载特别有效。

2. **Mod 下载的多轮重试策略**：
   ```
   镜像优先模式: mirror(10s) → mirror重试(10s) → official(30s)
   官方优先模式: official(20s) → mirror(10s) → official重试(30s) → mirror重试(30s)
   ```
   每个源有独立的超时，比我们现有的"统一超时逐个尝试"更精细。

3. **源失败自动禁用**：HTTP 502/404/DNS 失败 → 立即禁用该源；HTTP 403/429 → 仅对 BMCLAPI 容忍（BMCLAPI 高频返回 403 是正常的）。这种源级别的智能判断是我们缺少的。

4. **BMCLAPI 保护**：BMCLAPI URL 强制单线程 + 100ms 请求间隔。我们现有代码没有对 BMCLAPI 做任何限速保护。

5. **完整的 URL 重写表**（ModDownload.vb 1246-1310 行），我们 `sources.py` 缺少以下映射：
   ```
   libraries.minecraft.net → bmclapi2.bangbang93.com/libraries
   maven.minecraftforge.net → bmclapi2.bangbang93.com/maven
   maven.neoforged.net → bmclapi2.bangbang93.com/maven
   meta.fabricmc.net → bmclapi2.bangbang93.com/fabric-meta
   cdn.modrinth.com → mod.mcimirror.top
   mediafilez.forgecdn.net → mod.mcimirror.top
   api.curseforge.com → mod.mcimirror.top/curseforge
   ```

6. **级联失败熔断**：累计失败数超过 `min(10000, max(剩余文件*5.5, 线程限制*5.5+3))` 时强制终止整个下载任务，防止无限重试。

7. **IP 可靠性评分**：每个 IP 维护 -1 到 +0.5 的分数，DNS 解析时优先选高可靠 IP。这对国内网络环境极有价值。

### HMCL：下载架构的优雅抽象

**你要读的文件：**

- `references/HMCL/HMCLCore/src/main/java/org/jackhuang/hmcl/download/DownloadProvider.java` — 核心接口，6 个方法
- `references/HMCL/HMCLCore/src/main/java/org/jackhuang/hmcl/download/BMCLAPIDownloadProvider.java` — BMCLAPI 实现，前缀替换 + 候选 URL 逻辑
- `references/HMCL/HMCLCore/src/main/java/org/jackhuang/hmcl/download/AutoDownloadProvider.java` — 组合 Provider，聚合多个源的候选 URL
- `references/HMCL/HMCLCore/src/main/java/org/jackhuang/hmcl/download/MojangDownloadProvider.java` — 官方源实现
- `references/HMCL/HMCLCore/src/main/java/org/jackhuang/hmcl/download/MultipleSourceVersionList.java` — 顺序回退版本列表
- `references/HMCL/HMCLCore/src/main/java/org/jackhuang/hmcl/task/FetchTask.java` — 下载任务基类，并发控制 + URI 候选 + 重试

**关键参考模式：**

1. **DownloadProvider 接口**：核心是 `injectURL(baseURL) -> String` 和 `injectURLWithCandidates(baseURL) -> List<URI>`。前者返回首选 URL，后者返回所有候选。建议将我们 `sources.py` 中的函数式 API 重构为类似的接口类。

2. **AutoDownloadProvider 组合模式**：维护 `versionListProviders` 和 `fileProviders` 两个列表。`injectURL` 用首选 Provider，`injectURLWithCandidates` 聚合所有 Provider 的候选。这正好匹配"国内镜像优先 + 官方源兜底"。

3. **BMCLAPIDownloadProvider 的候选 URL 逻辑**：
   - 如果主替换改变了 URL → 只返回镜像 URL（镜像优先）
   - 如果主替换没改变 URL → 检查备用替换，返回原始+备用两个候选
   - 这种"镜像能覆盖就用镜像，覆盖不了就保留原始+备用"的逻辑比简单的 URL 列表更智能。

4. **FetchTask 的 URI 顺序重试**：候选 URI 列表按顺序尝试，每个 URI 有 3 次重试（200ms 间隔）。全局 Semaphore 控制并发。

5. **BMCLAPI Hash 优化**：如果 BMCLAPI 响应头包含 `x-bmclapi-hash`，FetchTask 会检查本地缓存是否已有相同哈希的文件，有则跳过下载。

---

## 阶段四：客户端清洗 & EULA → 读 docker-minecraft-server

**你要读的文件：**

- `references/docker-minecraft-server/files/cf-exclude-include.json` — CurseForge 客户端 Mod 排除/包含列表（~170 条）
- `references/docker-minecraft-server/files/modrinth-exclude-include.json` — Modrinth 排除/包含列表（~100 条）
- `references/docker-minecraft-server/scripts/start-configuration` — EULA 前置检查逻辑
- `references/docker-minecraft-server/scripts/start-setupModpack` — Mod 文件列表处理

**关键参考模式：**

1. **三层过滤架构**（我们的 `blacklist.py` 仅有第一层）：
   - **globalExcludes**：全局排除列表（~170 个 project slug，远超我们的 60 个关键字）
   - **globalForceIncludes**：全局强制包含（某些被误标为客户端的 Mod 实际服务端需要）
   - **modpacks.\<slug\>.excludes/forceIncludes**：按整合包定制的覆盖规则

2. **黑名单应迁移到 JSON**：当前 `blacklist.py` 的硬编码集合应迁移为 JSON 配置文件（格式参考 cf-exclude-include.json），并支持：
   - slug 精确匹配（比关键字包含更准确）
   - forceIncludes 覆盖
   - 用户自定义扩展

3. **EULA 必须前置检查**：docker-minecraft-server 在 `start-configuration` 中将 EULA 检查放在**所有其他步骤之前**，且明确禁止通过整合包的环境文件绕过。这与 PRD "严禁静默生成已同意的 eula.txt" 完全一致。确保 `pipeline.py` 中 EULA 闸在文件操作之前执行。

4. **环境变量覆盖模式**：`CF_EXCLUDE_MODS` / `CF_FORCE_INCLUDE_MODS` 等环境变量允许用户动态覆盖黑名单。我们可以在 EULA 闸交互时同时提供黑名单预览和自定义选项。

---

## 阶段五：交付 → 读 mc-server-runner

**你要读的文件：**

- `references/mc-server-runner/main.go` — 进程管理、信号处理、优雅关机
- `references/mc-server-runner/memory.go` — OOM 退出码诊断

**关键参考模式：**

1. **退出码传播**：mc-server-runner 将子进程的退出码直接透传。我们的完整性校验应关注退出码 137（OOM kill）的特殊含义。

2. **RCON + stdin 双路径命令**：`sendCommand()` 优先走 RCON，RCON 不可用时走 stdin。这对 deliver 阶段验证服务端可用性有参考——可通过 RCON 发送 `list` 命令确认服务端存活。

---

## 实操步骤

当你开始实现 builder 某个功能时：

1. 确定子阶段，找到上表对应的参考项目
2. 用 Read 工具阅读"你要读的文件"中列出的文件
3. 在参考项目中找到与你正在实现的功能最相近的代码段
4. 将参考项目的模式适配为 Python 实现，写入对应子目录
5. 确保新代码与现有 `core/contracts/` 中的 Pydantic 数据契约兼容
