# Cross-Layer Thinking Guide

> **Purpose**: Think through data flow across layers before implementing.

---

## The Problem

**Most bugs happen at layer boundaries**, not within layers.

Common cross-layer bugs in MC-SRE:

- CF manifest 只给 `(projectID, fileID)`，fetcher 拿不到真实文件名
- 下载引擎切换时 `fetch_all` 签名不一致
- 新增 `LoaderType` 枚举值但 sources.py / installer.py / script_gen.py 没同步
- URL 编码问题：CF CDN 路径中 `%2B` 未解码导致文件名不匹配

---

## Before Implementing Cross-Layer Features

### Step 1: Map the Data Flow

Draw out how data moves in MC-SRE:

```
用户 ZIP → unpack (UnpackResult) → metadata (Manifest) → fetcher (DownloadReport) → merge → install → deliver (BuildResult)
```

For each arrow, ask:

- What format is the data in? (Pydantic model? raw dict? file on disk?)
- What could go wrong? (missing fields? encoding issues? network failure?)
- Who is responsible for validation? (producer? consumer? both?)

### Step 2: Identify Boundaries

| Boundary | Common Issues |
|---|---|
| ZIP → unpack | Zip Slip, 中文文件名乱码, 畸形文件树 |
| unpack → metadata | 占位文件名 `{pid}-{fid}.jar` 未解析 |
| metadata → fetcher | URL 构造优先级错误, CF CDN 路径格式错误 |
| fetcher → merge | 缺失 mod 应降级而非熔断 |
| merge → deliver | EULA 未签, 客户端 mod 未清洗 |
| observer → brain | 事件防抖不足导致重复诊断 |
| brain → memory | 错误经验污染知识库 |

### Step 3: Define Contracts

For each boundary, the contract is defined in `core/contracts/`:

- What is the exact input Pydantic model?
- What is the exact output Pydantic model?
- What errors can occur (which `BuildError` subclass)?

---

## MC-SRE 枚举扩展：跨层一致性检查

当新增 `LoaderType` / `InputMode` / `ModSource` 等枚举值时，以下位置必须同步更新：

| 位置 | 文件 | 需更新内容 |
|---|---|---|
| 枚举定义 | `core/contracts/manifest.py` | 新增枚举成员 |
| URL 构造 | `builder/fetcher/sources.py` | 新增 URL 构造逻辑 |
| 安装器 | `builder/install/installer.py` | 新增安装命令 |
| 启动脚本 | `builder/launch/script_gen.py` | 新增启动方式 |
| 契约文档 | `.trellis/spec/builder/contracts.md` | 更新契约表 |

---

## URL 编码跨层陷阱

CurseForge CDN 的文件名可能包含 `+` 号，被编码为 `%2B`。

**问题链**：
1. CF API 返回 `fileName` 含 `%2B`
2. `cf_resolver.py` 的 `_decode_filename()` 解码为 `+`
3. `sources.py` 的 `_cf_cdn_path()` 用解码后文件名构造 URL
4. `sources.py` 的 `_decode_url_path()` 再次确保路径部分未编码
5. aria2c 的 `out=` 参数用解码后的文件名
6. 磁盘文件名 = 解码后的文件名

如果任一环节遗漏解码，会导致：
- 磁盘文件名与代码检查的文件名不一致
- 重试循环中永远找不到已下载的文件
- `missing_mods.log` 误报缺失

参考文件：`builder/fetcher/cf_resolver.py:47-73`

---

## 引擎切换跨层一致性

两种下载引擎（aria2c / httpx）共享同一个 `fetch_all()` 签名：

```python
async def fetch_all(
    manifest: Manifest,
    sandbox: Path,
    *,
    client=None,       # httpx 引擎用；aria2c 忽略
    concurrency=None,
    timeout=...,
) -> DownloadReport
```

新增引擎时必须：

- [ ] 实现相同的 `fetch_all()` 签名
- [ ] 在 `get_fetcher()` 中注册引擎名称
- [ ] 在 `core/config.py` 的 `Settings.download_engine` 注释中列出可用引擎
- [ ] 返回相同的 `DownloadReport` 结构

参考文件：`builder/fetcher/__init__.py:19-49`

---

## 常见跨层错误模式

### 错误 1：CF 占位文件名传入下载

**问题**：CF manifest 只给 `(projectID, fileID)`，未解析真实文件名就传入 fetcher，导致 URL 无法构造。

**正确流程**：`pipeline._parse_manifest_with_resolve()` 先调用 `resolve_batch()` 解析文件名，再传入 fetcher。

### 错误 2：缺失 mod 当异常处理

**问题**：下载失败的 mod 不应熔断整个流水线，服主可以后续手动补全。

**正确行为**：降级记录到 `missing_mods.log`，交付时在 `BuildResult.missing` 中透传。

### 错误 3：EULA 闸绕过

**问题**：直接写 `eula=true` 而不经 `EulaGate` 协议确认。

**正确行为**：必须经 `ensure_eula()` → `EulaGate.request()` → 用户确认 → `write_eula()`。

### 错误 4：硬盘路径在配置和路径常量间漂移

**问题**：`core/paths.py` 定义默认路径，`core/config.py` 允许环境变量覆盖，但派生函数仍读路径常量。

**正确行为**：派生函数应优先使用 `settings` 中的配置值，路径常量仅作为默认值。

---

## Checklist for Cross-Layer Features

Before implementation:

- [ ] Mapped the complete data flow (阶段 → 阶段 → 阶段)
- [ ] Identified all layer boundaries and their Pydantic contracts
- [ ] Defined format at each boundary (model type, not just "dict")
- [ ] Decided where validation happens (producer? consumer? both?)

After implementation:

- [ ] Tested with edge cases (null, empty, invalid, 0-byte file)
- [ ] Verified error handling at each boundary (BuildError subclass)
- [ ] Checked data survives round-trip (Manifest → fetcher → DownloadReport → BuildResult)
- [ ] Checked that consumers use shared Pydantic models, not local dict casts
- [ ] Enum changes propagated to all consumers (sources.py, installer.py, script_gen.py)
