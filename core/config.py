"""core.config — 全局配置加载入口。

配置优先级（高→低）：
  1. 环境变量（适合 CI/CD、Docker 部署）
  2. .env 文件（适合本地开发，不入版本控制）
  3. 代码内默认值

使用方式：
  from core.config import settings
  api_key = settings.cf_api_key
"""
from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


def _load_dotenv() -> dict[str, str]:
    """简易 .env 加载器（不引入 python-dotenv 依赖）。

    支持：
      - KEY=VALUE 格式
      - # 开头的注释行
      - 空行忽略
      - 引号包裹的值自动去除
    """
    env: dict[str, str] = {}
    if not _ENV_FILE.is_file():
        return env

    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # 去除引号
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        env[key] = value

    return env


@dataclass
class Settings:
    """全局配置项。"""

    # ──────────── CurseForge ────────────
    cf_api_key: str = ""
    """CurseForge Core API Key。
    
    申请地址：https://console.curseforge.com
    有了 API Key 后：
      - 可直接调用 /v1/mods/{pid}/files/{fid}/download-url 获取正版下载链接
      - 下载速度不受 CDN 限速
      - 无需 cloudscraper 绕过 Cloudflare
    """

    # ──────────── 下载 ────────────
    download_concurrency: int = 32
    """全局下载并发数。"""

    download_timeout: float = 30.0
    """单个 URL 下载超时（秒）。"""

    # ──────────── Java ────────────
    java_path: str = ""
    """Java 路径（空=自动探测）。"""

    java_min_version: int = 0
    """最低 Java 版本要求（0=不限，MC 1.21+ 自动设为 21）。"""

    # ──────────── 路径 ────────────
    sandbox_dir: str = str(_PROJECT_ROOT / ".sandbox")
    """构建沙箱目录。"""

    server_pool_dir: str = str(_PROJECT_ROOT / "server_pool")
    """服务端交付池目录。"""

    cache_dir: str = str(_PROJECT_ROOT / ".cache")
    """下载缓存目录。"""


def _build_settings() -> Settings:
    """从环境变量 + .env 文件构建 Settings。"""
    env = _load_dotenv()

    def _get(key: str, default: str = "") -> str:
        """优先取真实环境变量，其次取 .env 文件。"""
        return os.environ.get(key, env.get(key, default))

    return Settings(
        cf_api_key=_get("CF_API_KEY"),
        download_concurrency=int(_get("DOWNLOAD_CONCURRENCY", "32")),
        download_timeout=float(_get("DOWNLOAD_TIMEOUT", "30")),
        java_path=_get("JAVA_PATH"),
        java_min_version=int(_get("JAVA_MIN_VERSION", "0")),
        sandbox_dir=_get("SANDBOX_DIR", str(_PROJECT_ROOT / ".sandbox")),
        server_pool_dir=_get("SERVER_POOL_DIR", str(_PROJECT_ROOT / "server_pool")),
        cache_dir=_get("CACHE_DIR", str(_PROJECT_ROOT / ".cache")),
    )


# 全局单例
settings = _build_settings()
