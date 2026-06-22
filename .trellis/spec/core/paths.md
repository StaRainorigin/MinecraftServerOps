# 路径管理

> `core/paths.py` — 实例根目录 / 快照隔离区 / server_pool / 临时沙箱等路径常量的单一来源

---

## 核心规则

**所有持久化与中间态路径必须经 `core/paths.py` 派生，禁止在业务代码中硬编码路径。**

---

## 路径常量

| 常量 | 值 | 用途 |
|---|---|---|
| `BASE_DIR` | 项目根目录 | 其他路径的锚点 |
| `SERVER_POOL` | `BASE_DIR / "server_pool"` | 持久化交付池 |
| `SANDBOX_ROOT` | `BASE_DIR / ".sandbox"` | 构建期间的临时沙箱 |
| `SNAPSHOT_ROOT` | `BASE_DIR / ".snapshots"` | brain 模块事务性快照隔离区 |
| `DOWNLOAD_CACHE` | `BASE_DIR / ".cache" / "downloads"` | 构建期间的下载缓存 |

参考文件：`core/paths.py:10-23`

---

## 派生函数

| 函数 | 返回 | 用途 |
|---|---|---|
| `instance_path(id)` | `SERVER_POOL / f"instance_{id}"` | 某实例的持久化工作目录 |
| `sandbox_path(id)` | `SANDBOX_ROOT / f"build_{id}"` | 某次构建的临时沙箱目录 |
| `snapshot_path(id)` | `SNAPSHOT_ROOT / f"instance_{id}"` | 某实例的事务性快照目录 |
| `ensure_dirs()` | None | 初始化所有顶层目录 |

---

## 路径 vs 配置

- **路径常量**（`core/paths.py`）：固定结构，不适合用户配置
- **可配置路径**（`core/config.py`）：可通过环境变量覆盖，如 `SANDBOX_DIR`、`SERVER_POOL_DIR`

当需要可配置路径时，在 `Settings` 中添加对应字段（带环境变量绑定），但派生函数仍以 `core/paths.py` 为单一来源。

---

## 反模式

- [禁止] 在业务代码中硬编码 `Path("server_pool")` 或 `Path(".sandbox")`
- [禁止] 使用 `os.path.join` 而非 `Path` 的 `/` 运算符
- [禁止] 在 `core/paths.py` 外定义新的路径常量
