"""builder.deliver.publisher — 阶段五·目录交付。

将整理好的完全态服务端文件夹移动到持久化存储区域（server_pool/instance_*/），
并向用户或下游系统返回工作目录的绝对路径、文件大小以及模组总数报告。
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from core.contracts import BuildResult, InputMode, MissingMod
from core.paths import instance_path

logger = logging.getLogger(__name__)


def publish(
    sandbox: Path,
    instance_id: str,
    mode: InputMode,
    missing: list[MissingMod] | None = None,
) -> BuildResult:
    """将沙箱目录交付到持久化存储并生成报告。

    Args:
        sandbox: 构建完成的沙箱目录。
        instance_id: 实例 ID（如 "001"）。
        mode: 输入模式。
        missing: 全网断流未能下载的模组列表。

    Returns:
        BuildResult（含绝对路径、总大小、模组数、缺失列表）。

    Raises:
        FileExistsError: 目标实例目录已存在（防止覆盖）。
    """
    dest = instance_path(instance_id)

    # 如果目标已存在，先清理（支持重复构建）
    if dest.exists():
        logger.info("目标实例目录已存在，清理后覆盖: %s", dest)
        try:
            shutil.rmtree(str(dest), ignore_errors=True)
        except Exception:
            pass
        # 如果 rmtree 失败（文件被锁），降级为 dirs_exist_ok 的 copytree
        if dest.exists():
            logger.warning("无法完全清理目标目录，将覆盖已有文件")

    # 移动整个沙箱到交付池（如果被占用则用 copytree）
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if dest.exists():
            # 目标已存在（部分清理后残留），用 copytree 覆盖
            shutil.copytree(str(sandbox), str(dest), dirs_exist_ok=True)
            try:
                shutil.rmtree(str(sandbox), ignore_errors=True)
            except Exception:
                pass
        else:
            shutil.move(str(sandbox), str(dest))
    except (PermissionError, shutil.Error) as exc:
        # Windows 下文件可能被其他进程占用（如后台下载），降级为复制
        logger.warning("移动失败（%s），降级为复制...", exc)
        shutil.copytree(str(sandbox), str(dest), dirs_exist_ok=True)
        # 尝试清理源目录（忽略失败）
        try:
            shutil.rmtree(str(sandbox), ignore_errors=True)
        except Exception:
            pass
    logger.info("已交付到: %s", dest)

    # 统计
    total_size = _calc_dir_size(dest)
    mod_count = _count_mods(dest)

    result = BuildResult(
        workspace_path=dest,
        total_size_bytes=total_size,
        mod_count=mod_count,
        mode=mode,
        missing=missing or [],
    )

    logger.info(
        "交付报告：路径=%s, 大小=%s, 模组数=%d, 缺失=%d",
        dest,
        _human_size(total_size),
        mod_count,
        len(result.missing),
    )
    if result.missing:
        for m in result.missing:
            logger.warning("  缺失: %s (%s)", m.entry.filename, m.reason)

    return result


def _calc_dir_size(d: Path) -> int:
    """递归计算目录总字节数。"""
    total = 0
    try:
        for f in d.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    except (PermissionError, FileNotFoundError):
        pass
    return total


def _count_mods(d: Path) -> int:
    """统计 mods/ 下有效的 .jar 数（排除 .disabled）。"""
    mods_dir = d / "mods"
    if not mods_dir.is_dir():
        return 0
    return sum(
        1
        for f in mods_dir.iterdir()
        if f.is_file() and f.suffix.lower() == ".jar"
    )


def _human_size(n: int) -> str:
    """字节数转人类可读。"""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"
