# MC-SRE Builder 设计文档与使用指南

> 版本: 1.0 · 最后更新: 2026-06-18
> 对应 PRD: 核心功能 PRD V2 — 多模态服务端工作目录构建

---

## 目录

1. [架构总览](#1-架构总览)
2. [流水线设计](#2-流水线设计)
3. [数据契约](#3-数据契约)
4. [阶段详解](#4-阶段详解)
5. [异常与熔断机制](#5-异常与熔断机制)
6. [依赖注入与可测试性](#6-依赖注入与可测试性)
7. [使用方法](#7-使用方法)
8. [目录结构速查](#8-目录结构速查)

---

## 1. 架构总览

### 1.1 定位

Builder 是 MC-SRE 系统的入口级核心模块，专注完成服务器文件生命周期的 **"从 0 到 1"**——将多种用户输入源（引导包 / 完整客户端）全自动编译为开箱即用的服务端工作目录。

本阶段不涉及容器点火与实时监控，输出为磁盘上结构完备、依赖完整的工作目录。

### 1.2 核心设计原则

| 原则 | 体现 |
|------|------|
| **契约先行** | 模块间仅通过 `core/contracts/` 中的 Pydantic 模型通信，禁止裸 dict |
| **路径单一来源** | 所有持久化路径经 `core/paths.py` 统一管理，便于实例隔离 |
| **安全第一** | Zip Slip 防御、路径穿越拦截、EULA 严禁静默写入 |
| **依赖注入** | 外部依赖（httpx client / EULA 闸）可注入替换，默认提供可跑实现 |
| **优雅降级** | 全网断流不卡死，记 missing_mods.log 跳过继续；EULA 拒绝即熔断 |

### 1.3 多态输入分流

```
               ┌── 模式 A: 引导包 ──> 解析清单 ──> [多源云端下载] ──┐
[用户上传 ZIP]─┤                                                    ├──> [EULA闸] ──> 交付
               └── 模式 B: 客户端 ──> 扫描目录  ──> [本地剥离清洗] ──┘
```

- **模式 A（BOOTSTRAP）**：CurseForge / Modrinth 引导包，仅含元数据清单，需要云端下载
- **模式 B（CLIENT）**：完整游戏客户端，含 mods/*.jar 实体，需要本地清洗
- **模式 C（NATURAL）**：自然语言需求，本阶段待定，枚举值已预留

### 1.4 异步架构

Pipeline 主体为 `async def`，原因：

| 阶段 | 同步/异步 | 理由 |
|------|----------|------|
| unpack | 同步 | 纯文件 I/O，Python zipfile 无原生 async |
| metadata | 同步 | 纯 JSON 解析 |
| fetcher | **异步** | httpx.AsyncClient 网络并发下载 |
| merge (清洗/归并) | 同步 | 纯文件操作 |
| merge (EULA闸) | **异步** | 等待用户交互（可能超时 5 分钟） |
| deliver | 同步 | 纯文件校验与移动 |

---

## 2. 流水线设计

### 2.1 总调度函数签名

```python
async def build_workspace(
    zip_path: Path,          # 用户上传的 ZIP 路径
    instance_id: str,        # 实例 ID（如 "001"）
    *,
    eula_gate: EulaGate | None = None,       # 注入：EULA 确认闸
    http_client: httpx.AsyncClient | None = None,  # 注入：HTTP 客户端
) -> BuildResult
```

### 2.2 五阶段流转

```python
async def build_workspace(...):
    # ────────── 阶段一：多态解包与资产校验 ──────────
    sandbox = sandbox_path(build_id)          # 分配临时沙箱
    extract_zip(zip_path, sandbox)            # 安全解压（Zip Slip 防御）
    game_root = locate_game_root(sandbox)     # 畸形文件树 DFS 下钻
    mode = discriminate(game_root)            # 引导包 vs 客户端判别

    # ────────── 阶段二+三（仅引导包）──────────
    if mode == BOOTSTRAP:
        manifest = parse_manifest(manifest_path)  # 解析 CF/Modrinth 清单
        report = await fetch_all(manifest, sandbox)  # httpx 并发下载

    # ────────── 阶段四：资产合并与配置组装 ──────────
    if mode == CLIENT:
        clean_client_mods(mods_dir)           # 黑名单 Mod → .disabled
    merge_configs(src_root, dest_root)        # config/kubejs 归并
    await ensure_eula(dest_root, gate)        # EULA 确认闸（必须交互）

    # ────────── 阶段五：工作目录编译与交付 ──────────
    verify_integrity(dest_root, mode)         # 封账校验
    result = publish(dest_root, instance_id)  # 移入 server_pool/
    return result
```

### 2.3 异常清理策略

任何阶段抛异常 → pipeline 自动清理本次沙箱目录（`shutil.rmtree`），防止临时文件残留。EULA 拒绝/超时同样触发清理。

---

## 3. 数据契约

所有契约定义在 `core/contracts/`，基于 Pydantic v2，模块间禁止裸 dict 传递。

### 3.1 Manifest（整合包元数据）

```python
class Manifest(BaseModel):
    mc_version: str              # "1.20.1"
    loader_type: LoaderType      # FORGE / FABRIC / NEOFORGE / QUILT / VANILLA / PAPER
    loader_version: str | None   # "47.1.3" / None (VANILLA)
    mods: list[ModEntry]         # 模组列表
    source: ModSource            # CURSEFORGE / MODRINTH
    raw_path: str | None         # 原始清单文件路径（追溯用）
```

### 3.2 ModEntry（单模组标识）

```python
class ModEntry(BaseModel):
    source: ModSource            # CURSEFORGE / MODRINTH
    project_id: str              # CurseForge 用 projectID+fileID 定位
    file_id: str                 # Modrinth 不需要，直接带 downloads URL
    filename: str                # 目标文件名
    required: bool = True        # 是否必需
    direct_urls: list[str]       # Modrinth 自带的直接下载地址
    hashes: dict[str, str]       # {"sha1": "...", "sha512": "..."}
```

### 3.3 BuildResult（最终交付）

```python
class BuildResult(BaseModel):
    workspace_path: Path         # 交付目录绝对路径
    total_size_bytes: int        # 目录总大小
    mod_count: int               # 有效 .jar 数
    mode: InputMode              # BOOTSTRAP / CLIENT
    missing: list[MissingMod]    # 全网断流未能下载的模组
    manifest: Manifest | None    # 透传引导包清单（便于上层复用）
```

### 3.4 其他契约

| 契约 | 用途 |
|------|------|
| `InputMode` | 输入模式枚举：BOOTSTRAP / CLIENT / NATURAL |
| `EulaDecision` | EULA 用户决定：ACCEPTED / REJECTED / TIMEOUT |
| `UnpackResult` | 阶段一产物：沙箱路径 + 模式 + 游戏根 + 清单路径 |
| `DownloadReport` | 阶段三产物：成功列表 + 缺失列表 + 核心产物路径 |
| `MissingMod` | 断流记录：ModEntry + 原因 + 尝试过的源 |
| `IntegrityReport` | 阶段五校验：ok + 问题列表 |

---

## 4. 阶段详解

### 4.1 阶段一：多态解包与资产校验

#### safe_extract.py — 安全解压

**核心防御：Zip Slip（目录穿越）**

```python
# 对每个 ZIP entry，计算目标路径的规范化绝对路径
target = (dest_resolved / name).resolve()
# 必须以沙箱根为前缀，否则拒绝
target.relative_to(dest_resolved)  # ValueError = 穿越
```

**中文文件名修复**：zipfile 在 Windows 上默认 cp437 解码，中文变乱码。回退链：`cp437 → gbk → utf-8`

#### root_locator.py — 畸形文件树自适应

**问题**：玩家压缩时常多包一层"我的整合包"文件夹，解压出来先是一个空壳目录。

**策略**：
1. 若当前目录像游戏根 → 直接返回
2. 若一级只有一个子目录 → 递归下钻（最多 5 层）
3. 认定"游戏根"的信号：`mods/`、`config/`、`manifest.json`、`modrinth.index.json`、`.jar` 文件等

#### discriminator.py — 输入模式判别

**优先级**：
1. 存在有效 `manifest.json`（含 `minecraft`/`manifestType` 字段）或 `modrinth.index.json` → **BOOTSTRAP**
2. 存在 `mods/` 且含 `.jar`，或根目录有 `.jar` → **CLIENT**
3. 均不匹配 → 抛 `UnrecognizedPackError`

清单有效性校验：不仅检查文件名，还 `json.load` 验证内部结构，排除同名无关文件。

---

### 4.2 阶段二：元数据提取（仅引导包）

| 解析器 | 输入 | 提取内容 |
|--------|------|---------|
| `curseforge.py` | `manifest.json` | mc_version / loader(从 `"forge-47.1.3"` 解析) / files[].projectID+fileID |
| `modrinth.py` | `modrinth.index.json` | mc_version / loader / files[].downloads(直接URL) / hashes |
| `schema.py` | 统一分发 | 根据文件名自动选解析器，输出统一 `Manifest` |

**CurseForge 特点**：模组只有 `(projectID, fileID)` 对，需要后续通过 CDN 拼接下载 URL。

**Modrinth 特点**：文件清单直接携带 `downloads` URL 和 `hashes`，填充到 `ModEntry.direct_urls`，fetcher 可直接使用。

---

### 4.3 阶段三：云端多源依赖解析与下载

#### 多源定义（sources.py）

| 源 | base_url | 优先级 | 覆盖范围 |
|----|----------|--------|---------|
| BMCLAPI | `bmclapi2.bangbang93.com` | 最高 | 核心 / Forge / CF Mod 镜像 |
| Mojang Official | `piston-meta.mojang.com` | 低 | 原版核心 |
| CurseForge CDN | `mediafilez.forgecdn.net` | 低 | CF 模组文件 |
| Modrinth CDN | `cdn.modrinth.com` | 低 | Modrinth 模组 |

**URL 构造策略**：
- **服务端核心**：BMCLAPI 镜像优先 → 官方回退
- **Forge/NeoForge**：BMCLAPI installer 镜像 → maven 官方
- **Fabric/Quilt**：BMCLAPI fabric-meta → 官方 meta
- **CF 模组**：`/files/{projectID}/{fileID}/{filename}` → BMCLAPI 镜像回退
- **Modrinth 模组**：直接使用清单中的 `direct_urls`

#### 并发下载（downloader.py）

```
asyncio.Semaphore(concurrency=8)  ← 限流
    ├── _download_mod(entry_1)  ← 逐源尝试，成功即停
    ├── _download_mod(entry_2)
    ├── ...
    └── _download_server_jar()  ← 核心/安装器

单文件流程：URL_1 → 失败 → URL_2 → 失败 → ... → 全失败 → 记入 missing
```

**容错**：
- 单 URL 超时 120s，HTTP 错误自动切换下一个源
- 写了一半的文件自动清理（`dest.unlink()`）
- 全部失败记入 `MissingMod`，写 `missing_mods.log`

---

### 4.4 阶段四：资产合并与配置组装

#### blacklist.py — 纯客户端模组黑名单

40+ 关键字集合（小写匹配），覆盖：

| 类别 | 代表 |
|------|------|
| 渲染/光影 | Optifine, Sodium, Iris, Oculus, Rubidium, Embeddium, Starlight |
| 地图/UI | Xaero's Minimap, JourneyMap, REI, JEI, AppleSkin |
| 启动优化 | SmoothBoot, FastLoad, ModernFix |
| 音频/视觉 | SoundPhysics, Presence Footsteps, Dynamic FPS |
| 回放 | ReplayMod |

**匹配策略**：`.jar` 文件名去掉后缀转小写后，与黑名单关键字做**双向包含**匹配。

#### client_cleaner.py — 服务端清洗

- 遍历 `mods/*.jar`，命中黑名单 → **改后缀 `.disabled`**（可逆，非直接删除）
- 返回 `CleanReport`（含被禁用文件列表），便于审计

#### config_merger.py — 配置归并

归并目录列表：`config/`、`defaultconfigs/`、`kubejs/`、`serverconfig/`、`scripts/`

策略：`shutil.copy2` 递归复制，已存在则覆盖，不存在则创建。

#### eula_gate.py — EULA 交互闸

**核心约束：严禁静默生成已同意的 eula.txt。**

```
EulaGate (Protocol)            ← 接口定义
  ├── ConsoleEulaGate          ← 默认实现（控制台 input）
  └── [用户自定义: Web/Bot]    ← 注入替换

流程：
  1. 检查 eula.txt 是否已存在且同意（幂等）
  2. 展示 EULA 文本
  3. 等待用户确认（超时 5 分钟 → TIMEOUT）
  4. ACCEPTED → 写 eula=true
  5. REJECTED / TIMEOUT → 抛 EulaRejectedError 熔断
```

---

### 4.5 阶段五：工作目录编译与交付

#### integrity.py — 完整性校验

| 校验项 | 规则 |
|--------|------|
| EULA | `eula.txt` 存在且包含 `eula=true` |
| 服务端核心 | 根目录或一级子目录下存在非零 `.jar`（引导包模式强制） |
| Mod 完整性 | `mods/` 下无 0 字节 `.jar` |

#### publisher.py — 目录交付

1. 将沙箱目录 `shutil.move` 到 `server_pool/instance_{id}/`
2. 防覆盖：目标已存在则抛 `FileExistsError`
3. 统计：`total_size_bytes`（递归 walk）、`mod_count`（`mods/*.jar` 数）
4. 组装 `BuildResult`，缺失模组从 `missing_mods.log` 透传

---

## 5. 异常与熔断机制

| 异常 | 触发场景 | 处理 |
|------|---------|------|
| `ZipSlipError` | 解压时检测到目录穿越 | 立即终止解压，pipeline 清理沙箱 |
| `UnrecognizedPackError` | 既非引导包也非客户端 | pipeline 清理沙箱，提示用户 |
| `EulaRejectedError` | 用户拒绝/超时未确认 EULA | pipeline 清理沙箱，返回终止文案 |
| `IntegrityError` | 封账校验不通过（缺核心/缺 EULA） | pipeline 清理沙箱，列出问题 |
| `FileExistsError` | 目标实例目录已存在 | 拒绝覆盖，需用户指定新 ID |

**熔断顺序**：异常 → 清理本次沙箱（`_cleanup_sandbox`）→ 向上传播 → 调用方处理。

**降级**：下载全部断流 → **不熔断**，跳过记入 `missing_mods.log`，交付时提醒服主手动补全。

---

## 6. 依赖注入与可测试性

### 6.1 EULA 闸注入

```python
# 默认控制台交互
result = await build_workspace(zip_path, "001")

# 自定义闸（如 Web API 回调）
class MyEulaGate:
    async def request(self, timeout=300):
        # 调用前端 API 等待确认
        return EulaDecision.ACCEPTED

result = await build_workspace(zip_path, "001", eula_gate=MyEulGate())
```

### 6.2 HTTP 客户端注入

```python
# 测试时 mock
from unittest.mock import AsyncMock

mock_client = AsyncMock()
result = await build_workspace(zip_path, "001", http_client=mock_client)

# 真实运行（默认自动创建 httpx.AsyncClient）
result = await build_workspace(zip_path, "001")
```

### 6.3 路径隔离

所有路径通过 `core/paths.py` 派生，测试时可 monkeypatch 常量：

```python
import core.paths as paths
paths.SERVER_POOL = Path("/tmp/test_pool")
paths.SANDBOX_ROOT = Path("/tmp/test_sandbox")
```

---

## 7. 使用方法

### 7.1 CLI 启动

```bash
# 基本用法
python -m builder <zip_path> <instance_id>

# 示例
python -m builder my_modpack.zip 001
python -m builder D:\\packs\\client.zip my_server

# 详细日志
python -m builder my_modpack.zip 001 -v
```

**CLI 流程**：
1. 解压 → 判别模式
2. 引导包：解析清单 → 并发下载；客户端：黑名单清洗
3. 控制台弹出 EULA 确认（输入 Y/N，5 分钟超时）
4. 校验 → 交付 → 输出报告

**退出码**：
- `0` — 构建成功
- `1` — 构建失败（解包/下载/校验异常）
- `2` — EULA 拒绝/超时
- `130` — 用户 Ctrl+C 中断

### 7.2 Python API

```python
import asyncio
from pathlib import Path
from builder import build_workspace, EulaRejectedError, BuildError

async def main():
    try:
        result = await build_workspace(
            zip_path=Path("my_modpack.zip"),
            instance_id="001",
        )
        print(f"交付目录: {result.workspace_path}")
        print(f"模组数: {result.mod_count}")
        print(f"大小: {result.total_size_bytes} bytes")
        if result.missing:
            print(f"缺失 {len(result.missing)} 个模组，请手动补全")
    except EulaRejectedError as e:
        print(f"EULA 拒绝: {e}")
    except BuildError as e:
        print(f"构建失败: {e}")

asyncio.run(main())
```

### 7.3 自定义 EULA 闸

```python
from core.contracts import EulaDecision
from builder.merge.eula_gate import EulaGate

class WebApiEulaGate:
    """通过 Web API 等待用户确认的示例。"""

    async def request(self, timeout: float = 300) -> EulaDecision:
        # 1. 调用前端 API 展示 EULA 卡片
        # 2. 轮询等待用户点击
        # 3. 返回决定
        ...

result = await build_workspace(
    zip_path=Path("modpack.zip"),
    instance_id="001",
    eula_gate=WebApiEulaGate(),
)
```

### 7.4 产出目录结构

构建完成后，`server_pool/instance_001/` 内部结构示例：

```
instance_001/
├── eula.txt                        ← 已同意
├── server-forge-1.20.1.jar         ← 服务端核心/安装器
├── mods/
│   ├── Create-0.5.1f.jar           ← 服务端兼容模组
│   ├── JEI-15.2.0.27.jar.disabled  ← 已禁用的客户端模组
│   └── ...
├── config/
│   └── create.properties           ← 归并的配置文件
├── defaultconfigs/
├── kubejs/
└── missing_mods.log                ← 仅在有缺失时生成
```

---

## 8. 目录结构速查

```
builder/
├── __init__.py          # 包入口，导出 build_workspace + 异常类
├── __main__.py          # CLI 入口 (python -m builder)
├── pipeline.py          # 流水线总调度（async）
├── errors.py            # 异常类型定义
│
├── unpack/              # 阶段一：多态解包
│   ├── safe_extract.py  #   安全解压（Zip Slip 防御）
│   ├── root_locator.py  #   畸形文件树 DFS 下钻
│   └── discriminator.py #   输入模式判别
│
├── metadata/            # 阶段二：元数据提取（仅引导包）
│   ├── curseforge.py    #   CF manifest.json 解析
│   ├── modrinth.py      #   Modrinth index.json 解析
│   └── schema.py        #   统一分发入口
│
├── fetcher/             # 阶段三：多源并发下载
│   ├── sources.py       #   源定义 + URL 构造
│   ├── downloader.py    #   httpx+asyncio 并发下载
│   └── missing_log.py   #   全网断流日志
│
├── merge/               # 阶段四：资产合并与配置组装
│   ├── blacklist.py     #   纯客户端模组黑名单
│   ├── client_cleaner.py#   扫描清洗（.disabled）
│   ├── config_merger.py #   config/kubejs 归并
│   └── eula_gate.py     #   EULA 交互闸（Protocol+默认实现）
│
└── deliver/             # 阶段五：编译与交付
    ├── integrity.py     #   完整性校验
    └── publisher.py     #   移入 server_pool + 生成报告
```

---

## 附录 A：下载源 URL 模板

| 资源类型 | BMCLAPI 镜像 | 官方/CDN |
|---------|-------------|---------|
| 原版核心 | `bmclapi2.bangbang93.com/version/{ver}/server` | `piston-meta.mojang.com/...` |
| Forge Installer | `.../forge/download/{ver}/forge-{ver}-{fv}/installer.jar` | `maven.minecraftforge.net/...` |
| Fabric Loader | `.../fabric-meta/{fv}` | `meta.fabricmc.net/...` |
| CF 模组 | `.../files/{pid}/{fid}/{filename}` | `mediafilez.forgecdn.net/...` |
| Modrinth 模组 | 直接使用清单中的 `downloads` URL | — |

## 附录 B：黑名单完整列表

```
optifine, sodium, iris, oculus, rubidium, embeddium, lithium, phosphor, starlight,
xaerominimap, xaeroworldmap, xaerominimapfairplay, journeymap, minimap, mapwriter,
antiqueatlas, rei, roughlyenoughitems, jei, justenoughitems, inventoryprofilesnext,
inventoryhud, appleskin, notenoughitems, smoothboot, smoothbootreloaded, fastload,
modernfix, soundphysics, presencefootsteps, dynamicfps, entityculling,
entitytexturefeatures, continuity, sodiumextras, fpsreducer, betterthirdperson,
betterf3, replaymod, bslshaders, complementaryshaders, seuspbr
```

可通过 `from builder.merge.blacklist import is_client_mod` 编程查询，或直接扩展 `_CLIENT_MOD_BLACKLIST` 集合。
