# 配置系统

> `core/config.py` — 全局配置加载入口

---

## 配置优先级（高→低）

1. **环境变量**（适合 CI/CD、Docker 部署）
2. **`.env` 文件**（适合本地开发，不入版本控制）
3. **代码内默认值**

---

## Settings dataclass

```python
@dataclass
class Settings:
    cf_api_key: str = ""           # CF_API_KEY
    download_engine: str = "aria2c"  # DOWNLOAD_ENGINE
    download_concurrency: int = 32  # DOWNLOAD_CONCURRENCY
    download_timeout: float = 30.0  # DOWNLOAD_TIMEOUT
    java_path: str = ""            # JAVA_PATH
    java_min_version: int = 0      # JAVA_MIN_VERSION
    sandbox_dir: str = ...         # SANDBOX_DIR
    server_pool_dir: str = ...     # SERVER_POOL_DIR
    cache_dir: str = ...           # CACHE_DIR
```

访问方式：`from core.config import settings`

参考文件：`core/config.py:53-93`

---

## .env 加载器

项目使用自研简易 `.env` 加载器，不依赖 `python-dotenv`。支持：
- `KEY=VALUE` 格式
- `#` 开头的注释行
- 引号包裹的值自动去除

参考文件：`core/config.py:23-49`

---

## 新增配置项的步骤

1. 在 `Settings` dataclass 中添加字段（带类型注解和默认值）
2. 在 `_build_settings()` 中添加环境变量绑定
3. 更新 `.env.example` 中的说明
4. 在此文档中记录

---

## 反模式

- [禁止] 直接读取 `os.environ` 而不经过 `Settings`（绕过 .env 和默认值）
- [禁止] 在 `Settings` 外定义全局配置变量
- [禁止] 引入 `python-dotenv` 依赖（项目已有自研加载器）
