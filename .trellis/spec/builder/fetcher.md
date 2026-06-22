# 下载引擎

> `builder/fetcher/` — 多源并发下载，支持引擎切换与重试

---

## 架构分层

| 层 | 文件 | 职责 |
|---|---|---|
| 引擎路由 | `fetcher/__init__.py` | `get_fetcher(engine)` 返回对应引擎的 `fetch_all` |
| URL 构造 | `fetcher/sources.py` | 为每个 mod 构造候选 URL 列表（镜像优先 → CDN 回退） |
| 传输引擎 | `fetcher/downloader.py` | aria2c 主力引擎（多连接、分块、重试、断点续传） |
| 传输引擎 | `fetcher/downloader_httpx.py` | httpx 备用引擎（源竞争、分块、慢速掐死） |
| CF 解析 | `fetcher/cf_resolver.py` | CurseForge 文件名解析（API Key / cloudscraper 双策略） |
| 结果汇报 | `fetcher/missing_log.py` | 缺失模组日志 |

两种引擎共享同一个 `fetch_all()` 函数签名，pipeline 无需感知引擎切换。

---

## 引擎切换机制

```python
# core/config.py
download_engine: str = "aria2c"  # 支持 DOWNLOAD_ENGINE 环境变量

# builder/fetcher/__init__.py
def get_fetcher(engine: str = "aria2c"):
    if engine == "aria2c":
        # 检测可用性，不可用时自动降级到 httpx
        ...
    elif engine == "httpx":
        ...
    else:
        raise ValueError(f"不支持的下载引擎: {engine}")
```

参考文件：`builder/fetcher/__init__.py:19-49`

---

## aria2c 引擎设计

### 输入文件格式

aria2c `--input-file` 标准格式：URL 在前（不缩进），`dir=`/`out=` 在后（空格缩进），空行分隔不同文件。同一文件的多个候选 URL 互为源，aria2c 自动竞争/回退。

```
https://mod.mcimirror.top/files/7471/280/mod.jar
https://mediafilez.forgecdn.net/files/7471/280/mod.jar
 dir=/path/to/mods
 out=mod.jar

```

### 已存在文件处理

预过滤：已存在的非空文件不写入输入文件，避免 aria2c 覆盖风险。配合 `--allow-overwrite=false` 双重保险。

### 重试策略

- 首轮下载完成后，失败文件自动进入重试循环
- 最多 3 轮重试（`_MAX_RETRY_ROUNDS = 3`）
- 每轮间隔 5 秒（让 CDN 冷却），降低并发到 8
- aria2c 全部重试用尽后，httpx 兜底再试一次（低并发 4，避免 CDN 封锁）

参考文件：`builder/fetcher/downloader.py:437-722`

---

## 多源 URL 构造

### 源优先级

| 源 | base_url | 优先级 | 覆盖范围 |
|---|---|---|---|
| BMCLAPI | `bmclapi2.bangbang93.com` | 0（最高） | 核心 / Forge / NeoForge 镜像 |
| Mojang Official | `piston-meta.mojang.com` | 10 | 原版核心 |
| MCIMirror | `mod.mcimirror.top` | 15 | CF Mod 镜像（PCL2 风格） |
| CurseForge Edge | `edge.forgecdn.net` | 20 | CF 模组文件 |
| CurseForge Media | `mediafilez.forgecdn.net` | 21 | CF 模组直连 |
| Modrinth CDN | `cdn.modrinth.com` | 20 | Modrinth 模组 |

### URL 构造策略

- **CF 模组**：mcimirror 优先 → direct_urls（cf_resolver 填充）→ edge → mediafilez
- **Modrinth 模组**：direct_urls 优先 → mcimirror 重写
- **服务端核心**：BMCLAPI 镜像优先 → 官方回退
- **NeoForge installer**：动态获取 installerPath（`resolve_neoforge_installer_url`）

参考文件：`builder/fetcher/sources.py:104-164`

---

## CurseForge 文件名解析

两种策略自动选择：

| 策略 | 条件 | 速度 | 限制 |
|---|---|---|---|
| A: CF Core API | 有 `CF_API_KEY` | 快 | 无限制 |
| B: cloudscraper | 无 API Key | 慢 | 可能被限流 |

结果缓存到 `.cache/cf_resolve_cache.json`，断点续传时跳过已解析条目。
解析失败的条目降级为 `{pid}-{fid}.jar` 占位文件名。

**URL 解码注意**：CF CDN 路径中 `+` 可能被编码为 `%2B`，必须用 `_decode_filename()` 和 `_decode_url_path()` 解码，否则磁盘文件名与代码检查的文件名不一致，导致重试死循环。

参考文件：`builder/fetcher/cf_resolver.py:47-73`

---

---

## 扩展点记录

### [EXP-1] 第三方混合端下载支持

- **位置**：`fetcher/sources.py` — URL 构造逻辑
- **现状**：`LoaderType.MIXED_MOHIST` / `MIXED_ARCLIGHT` 已预留枚举值，但 `sources.py` 中无对应 URL 构造
- **扩展时需新增**：
  1. Mohist/Arclight 官方下载 API URL（`mohistmc.com` / `arclight.icu`）
  2. 国内镜像源（如有）
  3. `build_mod_urls()` 中对混合端类型的分支处理
- **注意**：混合端安装器与 Forge/NeoForge 差异大，`install/installer.py` 也需同步扩展
- **详细决策记录**：见 `pipeline.md` EXP-1

---

## 反模式

- [禁止] 在 `build_mod_urls()` 外手动拼接 CF CDN URL（必须走 `_cf_cdn_path()` 格式）
- [禁止] 忽略 `_decode_filename()` 直接使用 CF 返回的原始文件名（`%2B` 问题）
- [禁止] 新增下载源但不设置 `priority`（优先级决定下载顺序）
- [禁止] 在 aria2c 输入文件中 `dir=`/`out=` 不缩进（会被识别为 URI）
- [禁止] 使用 `--allow-overwrite=true`（会覆盖已存在文件）
- [禁止] 使用 `--lowest-speed-limit`（高并发时误杀，已用 `--max-tries + --timeout` 替代）
