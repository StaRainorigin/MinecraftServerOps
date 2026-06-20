"""builder.merge.config_merger — 阶段四·配置文件全量归并。

将解压/下载产物中的 config/、defaultconfigs/、kubejs/ 等自定义目录全量复制到
最终工作目录。已存在的文件覆盖，不存在的自动创建。
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# 需要归并的目录名集合（小写匹配）
_CONFIG_DIRS = {
    "config",
    "defaultconfigs",
    "kubejs",
    "serverconfig",
    "scripts",
    # 部分整合包把配置放在 mods 目录下的子文件夹中
    # 这些文件已在 mods/ 中，不需额外处理
}


def merge_configs(src_root: Path, dest_root: Path) -> list[Path]:
    """将 src_root 下的配置目录全量归并到 dest_root。

    策略：
        - 遍历 _CONFIG_DIRS，src_root 下存在则递归复制到 dest_root 下同名目录。
        - dest 下已有同名文件直接覆盖（shutil.copy2 保留元数据）。
        - dest 下不存在对应目录则自动创建。

    Args:
        src_root: 源游戏根目录（解压/下载后的沙箱）。
        dest_root: 目标工作目录（最终交付的实例目录或沙箱内的合并目标）。

    Returns:
        已归并的文件路径列表。
    """
    merged: list[Path] = []

    for dir_name in _CONFIG_DIRS:
        src_dir = src_root / dir_name
        if not src_dir.is_dir():
            continue

        dest_dir = dest_root / dir_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        for item in src_dir.rglob("*"):
            if not item.is_file():
                continue
            relative = item.relative_to(src_dir)
            target = dest_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(target))
            merged.append(target)

    logger.info("配置归并完成：共复制 %d 个文件", len(merged))
    return merged
