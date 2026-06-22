# 数据契约

> `core/contracts/` — 所有跨阶段、跨模块的 Pydantic 模型定义

---

## 核心原则

**模块间仅通过 `core/contracts/` 中的 Pydantic 模型通信，禁止裸 `dict`。**

这是本项目最核心的架构约束。每个阶段的输入输出必须是 Pydantic 模型实例，
不允许在函数签名中出现 `dict` 或 `**kwargs` 传递业务数据。

---

## 契约清单

| 契约 | 文件 | 生产者 | 消费者 |
|---|---|---|---|
| `BuildSource` | `core/contracts/build_results.py` | 用户输入层 | pipeline 入口 |
| `Manifest` | `core/contracts/manifest.py` | metadata 阶段 | fetcher 阶段 |
| `ModEntry` | `core/contracts/manifest.py` | metadata 阶段 | fetcher / blacklist |
| `UnpackResult` | `core/contracts/build_results.py` | unpack 阶段 | pipeline |
| `DownloadReport` | `core/contracts/build_results.py` | fetcher 阶段 | pipeline / deliver |
| `MissingMod` | `core/contracts/build_results.py` | fetcher 阶段 | deliver / missing_log |
| `IntegrityReport` | `core/contracts/build_results.py` | deliver 阶段 | pipeline |
| `BuildResult` | `core/contracts/build_results.py` | deliver 阶段 | 上层调用方 |
| `InputMode` | `core/contracts/build_results.py` | discriminator | pipeline 全阶段 |
| `EulaDecision` | `core/contracts/build_results.py` | EulaGate | pipeline |
| `ServerProperties` | `core/contracts/build_results.py` | configure 阶段 | pipeline / 用户交互 |
| `SmokeTestResult` | `core/contracts/build_results.py` | smoke test 阶段 | pipeline / brain |
| `LoaderType` | `core/contracts/manifest.py` | metadata 阶段 | fetcher / install / launch |
| `ModSource` | `core/contracts/manifest.py` | metadata 阶段 | fetcher / cf_resolver |

---

## 枚举类型

### InputMode（输入模式）

```python
class InputMode(str, Enum):
    BOOTSTRAP = "bootstrap"        # 引导包（CF/Modrinth manifest）
    CLIENT = "client"              # 客户端 ZIP/文件夹
    SERVER = "server"              # 服务端 ZIP/文件夹
    PACK_SLUG = "pack_slug"        # 整合包名称搜索
    VANILLA = "vanilla"            # 原版构建（口述）
```

新增 `InputMode` 时，必须同步更新：
1. `core/contracts/build_results.py` — 枚举定义
2. `builder/unpack/discriminator.py` — 判别逻辑
3. `builder/pipeline.py` — 分支路由

### LoaderType（加载器类型）

```python
class LoaderType(str, Enum):
    VANILLA = "vanilla"
    FORGE = "forge"
    NEOFORGE = "neoforge"
    FABRIC = "fabric"
    QUILT = "quilt"
    PAPER = "paper"
    # [EXP-1] 第三方混合端预留
    MIXED_MOHIST = "mohist"        # 待实现，见 pipeline.md EXP-1
    MIXED_ARCLIGHT = "arclight"    # 待实现，见 pipeline.md EXP-1
```

新增加载器类型时，必须同步更新以下位置：
1. `core/contracts/manifest.py` — 枚举定义
2. `builder/fetcher/sources.py` — URL 构造逻辑
3. `builder/install/installer.py` — 安装器执行逻辑
4. `builder/launch/script_gen.py` — 启动脚本生成逻辑

### ModSource（模组来源）

```python
class ModSource(str, Enum):
    CURSEFORGE = "curseforge"
    MODRINTH = "modrinth"
    LOCAL = "local"                # 本地文件（客户端/服务端输入）
```

---

## 新增契约定义

### BuildSource（统一输入入口）

```python
class BuildSource(BaseModel):
    """用户构建请求的统一入口"""
    input_mode: InputMode
    path: Path | None = None              # ZIP/文件夹路径（BOOTSTRAP/CLIENT/SERVER）
    slug: str | None = None               # 整合包名称（PACK_SLUG）
    game_version: str | None = None       # 游戏版本（VANILLA）
    loader_type: LoaderType | None = None # 加载器类型（VANILLA）
    loader_version: str | None = None     # 加载器版本（VANILLA）
```

### ServerProperties（服务端配置）

```python
class ServerProperties(BaseModel):
    """server.properties 配置项"""
    online_mode: bool = True              # 正版验证
    enable_command_block: bool = False    # 命令方块
    allow_flight: bool = False            # 飞行
    pvp: bool = True                      # PVP
    max_players: int = 20                 # 最大玩家数
    view_distance: int = 10               # 视距
    # ... 其他标准 server.properties 字段按需添加
```

生产者：用户交互（configure 阶段收集）
消费者：`configure/server_properties.py`（写入文件）

### SmokeTestResult（开服验证结果）

```python
class SmokeTestResult(BaseModel):
    """开服验证结果"""
    passed: bool
    launch_seconds: float = 0.0           # 启动耗时
    crash_log_path: Path | None = None    # 崩溃日志路径（失败时）
    error_summary: str | None = None      # 崩溃原因摘要（失败时）
```

生产者：`smoke/validator.py`
消费者：pipeline（写入 `BuildResult`）/ brain（诊断与修复）

---

## 新增契约的规则

1. 在 `core/contracts/` 对应文件中定义 Pydantic `BaseModel`
2. 使用 `Field(default_factory=list)` 而非 `Field(default=[])` 避免可变默认值
3. 枚举类型继承 `(str, Enum)` 以支持 JSON 序列化
4. 在 `core/contracts/__init__.py` 中重新导出
5. 在此文档中记录生产者和消费者

---

## 反模式

- [禁止] 在阶段函数中返回 `dict` 而非 Pydantic 模型
- [禁止] 在 Pydantic 模型中使用 `Field(default=[])` （可变默认值陷阱）
- [禁止] 在枚举中新增值但不更新所有同步位置（见各枚举下方的同步清单）
- [禁止] 直接 `json.loads()` 后将结果当 Pydantic 模型用而不做校验
- [禁止] 新增 `InputMode` 但不在 `discriminator.py` 和 `pipeline.py` 中添加对应分支
