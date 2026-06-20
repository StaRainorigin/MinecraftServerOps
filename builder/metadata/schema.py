"""builder.metadata.schema — 阶段二·薄适配层：根据清单文件名分发到对应解析器。

上层只需调用 parse_manifest(path) 即可，无需关心是 CurseForge 还是 Modrinth。
"""
from __future__ import annotations

from pathlib import Path

from core.contracts import Manifest

from .curseforge import parse_curseforge
from .modrinth import parse_modrinth


def parse_manifest(manifest_path: Path) -> Manifest:
    """根据清单文件名自动分发到对应的解析器。

    Args:
        manifest_path: 清单文件路径（manifest.json 或 modrinth.index.json）。

    Returns:
        统一的 Manifest 实例。

    Raises:
        ValueError: 不支持的清单文件名。
    """
    name = manifest_path.name.lower()

    if name == "manifest.json":
        return parse_curseforge(manifest_path)
    if name == "modrinth.index.json":
        return parse_modrinth(manifest_path)

    raise ValueError(f"不支持的清单文件：{manifest_path.name}（仅支持 manifest.json / modrinth.index.json）")
