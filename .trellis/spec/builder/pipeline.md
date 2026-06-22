# 流水线架构

> `builder/pipeline.py` — 多阶段异步流水线总调度

---

## 总调度签名

```python
async def build_workspace(
    source: BuildSource,
    instance_id: str,
    *,
    eula_gate: EulaGate | None = None,
    http_client: httpx.AsyncClient | None = None,
    resume_sandbox: Path | None = None,
) -> BuildResult
```

- `source` 替代原 `zip_path`，支持多种输入类型（详见契约 `BuildSource`）
- 参考文件：`builder/pipeline.py:76`

---

## 输入类型与分支路由

系统根据用户输入自动判别处理分支：

```
BuildSource
  |
  ├── SERVER_ZIP / SERVER_DIR ──> 服务端分支
  |     ├── 完整服务端 ──────────> 直接交付（跳过下载/安装）
  |     └── 不完整服务端 ────────> 补全加载器 → 安装 → 交付
  |
  ├── CLIENT_ZIP / CLIENT_DIR ──> 客户端分支
  |     └── 提取加载器版本 → 拉取服务端核心 → 安装 → 合并客户端资产 → 清洗 → 交付
  |
  ├── BOOTSTRAP_ZIP ────────────> 引导包分支（原模式 A）
  |     └── 解包 → 提取 manifest → 多源下载 → 安装 → 合并 → 清洗 → 交付
  |
  ├── PACK_SLUG ────────────────> 整合包名称搜索分支
  |     └── CF/Modrinth API 搜索 → 优先取服务端 → 回退客户端/引导包
  |
  └── VANILLA ──────────────────> 原版构建分支（优先级最低）
        └── 用户口述版本 → 拉取核心 → 配置 → 交付
```

### 实现优先级

| 优先级 | 输入类型 | 状态 |
|---|---|---|
| 1 | BOOTSTRAP_ZIP（CF/Modrinth 引导包） | 已实现 |
| 2 | CLIENT_ZIP / CLIENT_DIR | 待实现 |
| 3 | SERVER_ZIP / SERVER_DIR | 待实现 |
| 4 | PACK_SLUG（整合包名称搜索） | 待实现 |
| 5 | VANILLA（原版构建） | 待实现 |

---

## 阶段流转

| 阶段 | 名称 | 同步/异步 | 适用分支 | 关键文件 |
|---|---|---|---|---|
| ① | 多态解包与资产校验 | 同步 | ZIP 类输入 | `unpack/safe_extract.py`, `unpack/root_locator.py`, `unpack/discriminator.py` |
| ② | 元数据提取 | 同步 | 引导包 / 客户端 / 服务端 | `metadata/curseforge.py`, `metadata/modrinth.py`, `metadata/schema.py` |
| ③ | 多源并发下载 | **异步** | 引导包 / 不完整服务端 | `fetcher/downloader.py`, `fetcher/sources.py` |
| ④ | 资产合并与配置组装 | 混合 | 客户端 / 引导包 | `merge/client_cleaner.py`, `merge/config_merger.py`, `merge/eula_gate.py`, `merge/optional_mods.py` |
| ⑤ | 服务端安装 | 同步 | 引导包 / 客户端 / 不完整服务端 | `install/installer.py`, `install/java_probe.py` |
| ⑥ | 工作目录编译与交付 | 同步 | 全部 | `deliver/integrity.py`, `deliver/publisher.py`, `launch/script_gen.py` |
| ⑦ | 服务端配置 | 同步 | 全部 | `configure/server_properties.py` |
| ⑧ | 开服验证（Smoke Test） | **异步** | 全部 | `smoke/launcher.py`, `smoke/validator.py` |

### 阶段跳过规则

- **完整服务端**：跳过 ②③④⑤，直接从 ⑥ 开始
- **客户端输入**：跳过 ③（无云端下载），但需 ② 提取加载器版本
- **引导包输入**：全阶段执行
- **原版构建**：跳过 ①②③④，仅 ⑤⑥⑦⑧

---

## 可选 Mod 处理

### 识别来源

| 来源 | 识别方式 | 处理 |
|---|---|---|
| CF/Modrinth manifest | `optional: true` 标记 | 展示给用户勾选，未勾选的以 `.jar.disabled` 后缀保留 |
| 国内整合包"可选mod"文件夹 | 目录名含"可选"/"optional" | 同上，以 `.jar.disabled` 后缀保留 |
| 客户端模式 | 无元数据，无法自动识别 | 不处理可选性，全部走黑名单清洗 |

### 统一后缀

所有可选但未启用的 mod 统一使用 `.jar.disabled` 后缀，而非删除或移出目录。理由：
- 用户后续可自行去掉 `.disabled` 启用
- 保留文件便于审计和问题排查
- 与 Forge/NeoForge 的 `.disabled` 惯例一致

参考文件：`builder/merge/optional_mods.py`（待实现）

---

## 服务端校验

### 语法校验（构建前，阶段 ① 内）

检查标志性文件判断输入是否为可用服务端：

- 存在 `.jar` 文件且文件名匹配已知服务端核心模式（`minecraft_server.*jar`、`forge-*jar`、`fabric-server*jar` 等）
- 存在 `mods/` 或 `libraries/` 等典型目录结构
- 不满足 → 标记为"不完整服务端"，走补全流程
- 完全无法识别 → 提示用户"无法识别为有效输入"，终止构建

### 语义校验（阶段 ⑧ Smoke Test）

启动服务端，观察是否在超时内正常完成初始化。这是唯一真正可靠的可用性验证。

- 验证失败 → 记录崩溃日志，返回 `BuildResult(smoke_passed=False)`
- 不在此阶段尝试自动修复（修复归 brain 模块）

---

## 客户端校验（构建前，阶段 ① 内）

检查标志性文件判断输入是否为可用客户端：

- 存在 `mods/` 目录且内有 `.jar`
- 或存在 `versions/` 目录下有版本 JSON
- 不满足 → 提示用户"无法识别为有效客户端"，让用户确认
- 客户端本身不可用 → 提示用户，不修

---

## 扩展点记录

### [EXP-1] 第三方混合端支持

- **位置**：`LoaderType` 枚举 + `fetcher/sources.py` + `install/installer.py`
- **预留**：`LoaderType` 中预留 `MIXED_MOHIST` / `MIXED_ARCLIGHT` 值
- **现状**：fetcher 阶段遇到混合端类型时抛 `NotImplementedError`
- **原因**：混合端 mod 兼容性不可控，安装流程差异大，现阶段投入产出比低
- **扩展条件**：基础流程稳定后，且有用户明确需求时再实现

### [EXP-2] 构建后增强钩子

- **位置**：pipeline 末尾，阶段 ⑧ 之后
- **预留**：`post_enhance` 钩子点，现阶段为空
- **潜在用途**：推荐安装 Save My Server Mod、Simple Voice Chat（需验证 UDP 25575）等
- **扩展条件**：基础流程闭环后，作为插件式扩展逐步添加

---

## 续传机制

当 `resume_sandbox` 指向已有未完成沙箱时，跳过解压阶段，直接从下载阶段继续。已存在的 mod 文件会被 `_generate_input_file()` 的"已存在"检测自动跳过。

参考文件：`builder/pipeline.py:117-153`

---

## 异常清理策略

任何阶段抛异常 → pipeline 自动清理本次沙箱目录（`shutil.rmtree`），防止临时文件残留。EULA 拒绝/超时同样触发清理。

```python
except EulaRejectedError:
    _cleanup_sandbox(sandbox)
    raise
except BuildError:
    _cleanup_sandbox(sandbox)
    raise
except Exception:
    _cleanup_sandbox(sandbox)
    raise
```

参考文件：`builder/pipeline.py:257-270`

---

## 反模式

- [禁止] 在 pipeline 外直接调用阶段函数而不处理异常清理
- [禁止] 跳过 EULA 闸直接写入 `eula=true`
- [禁止] 在同步阶段中使用 `asyncio.run()` 嵌套事件循环
- [禁止] 在阶段间传递裸 `dict` 而非 Pydantic 模型
- [禁止] 删除可选 mod 而非使用 `.jar.disabled` 后缀
- [禁止] 在 smoke test 阶段尝试自动修复（修复归 brain 模块）
