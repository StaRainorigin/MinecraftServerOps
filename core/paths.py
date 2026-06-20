"""core.paths — 实例根目录 / 快照隔离区 / server_pool / 临时沙箱等路径常量的单一来源。

所有持久化与中间态路径必须经此处派生，便于实例隔离与安全沙箱校验。
"""
from __future__ import annotations

from pathlib import Path

# 项目根目录（game_ops/）
BASE_DIR = Path(__file__).resolve().parent.parent

# 持久化交付池：每个实例一个目录（instance_xxx）
SERVER_POOL = BASE_DIR / "server_pool"

# 构建期间的临时沙箱：解包 / 清洗 / 下载都在此进行，完成后移动走
SANDBOX_ROOT = BASE_DIR / ".sandbox"

# brain 模块事务性快照隔离区（先定义，供后续模块使用）
SNAPSHOT_ROOT = BASE_DIR / ".snapshots"

# 构建期间的临时下载缓存（可被多实例复用，定期清理）
DOWNLOAD_CACHE = BASE_DIR / ".cache" / "downloads"


def instance_path(instance_id: str) -> Path:
    """返回某实例的持久化工作目录：server_pool/instance_<id>"""
    return SERVER_POOL / f"instance_{instance_id}"


def sandbox_path(build_id: str) -> Path:
    """返回某次构建的临时沙箱目录：.sandbox/build_<id>"""
    return SANDBOX_ROOT / f"build_{build_id}"


def snapshot_path(instance_id: str) -> Path:
    """返回某实例的事务性快照目录：.snapshots/instance_<id>"""
    return SNAPSHOT_ROOT / f"instance_{instance_id}"


def ensure_dirs() -> None:
    """初始化所有顶层目录（不存在则创建）。启动时调用一次。"""
    for p in (SERVER_POOL, SANDBOX_ROOT, SNAPSHOT_ROOT, DOWNLOAD_CACHE):
        p.mkdir(parents=True, exist_ok=True)
