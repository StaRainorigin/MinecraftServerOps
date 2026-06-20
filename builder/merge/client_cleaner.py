"""builder.merge.client_cleaner — 阶段四·服务端清洗。

扫描 mods/ 目录下的所有 .jar 文件，将命中的纯客户端模组改后缀为 .disabled，
防止服务端加载客户端渲染类代码导致崩溃。改后缀可逆，服主可手动恢复。
"""
from __future__ import annotations

import logging
from pathlib import Path

from .blacklist import is_client_mod

logger = logging.getLogger(__name__)


def clean_client_mods(mods_dir: Path) -> CleanReport:
    """清洗 mods/ 目录中的纯客户端模组。

    遍历所有 .jar 文件，命中黑名单 → 改后缀 .disabled（不直接删除）。

    Args:
        mods_dir: 服务端 mods 目录。

    Returns:
        CleanReport（含被禁用的文件列表）。
    """
    if not mods_dir.is_dir():
        logger.info("mods/ 目录不存在，跳过清洗: %s", mods_dir)
        return CleanReport(disabled=[])

    disabled: list[Path] = []
    for jar in mods_dir.iterdir():
        if not jar.is_file() or jar.suffix.lower() != ".jar":
            continue
        if is_client_mod(jar.name):
            target = jar.with_suffix(jar.suffix + ".disabled")
            jar.rename(target)
            disabled.append(target)
            logger.info("已禁用客户端模组: %s", jar.name)

    logger.info("清洗完成：共禁用 %d 个客户端模组", len(disabled))
    return CleanReport(disabled=disabled)


class CleanReport:
    """清洗结果报告。"""

    def __init__(self, disabled: list[Path]) -> None:
        self.disabled = disabled

    @property
    def count(self) -> int:
        return len(self.disabled)
