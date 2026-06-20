"""builder.metadata.modrinth — 阶段二·解析 Modrinth modrinth.index.json 索引。

Modrinth 导出的 modrinth.index.json 典型结构：
{
  "formatVersion": 1,
  "game": "minecraft",
  "versionId": "1.0.0",
  "dependencies": [
    { "projectID": "P7dR8mSH", "versionId": "HqHuqf94", "dependencyType": "required" },
    { "projectID": "fabric-loader", "versionId": "0.14.22", "dependencyType": "required" },
    { "projectID": "minecraft", "versionId": "1.20.1", "dependencyType": "required" }
  ],
  "files": [
    { "path": "mods/mod_a.jar", "hashes": {"sha1": "..."}, "downloads": ["https://..."] },
    ...
  ]
}
"""
from __future__ import annotations

import json
from pathlib import Path

from core.contracts import LoaderType, Manifest, ModEntry, ModSource

# Modrinth 加载器的 projectID → LoaderType
_MODRINTH_LOADER_MAP: dict[str, LoaderType] = {
    "fabric-loader": LoaderType.FABRIC,
    "forge": LoaderType.FORGE,
    "neoforge": LoaderType.NEOFORGE,
    "quilt-loader": LoaderType.QUILT,
}


def parse_modrinth(index_path: Path) -> Manifest:
    """解析 Modrinth modrinth.index.json，产出统一的 Manifest。

    Modrinth 文件清单直接携带 downloads URL，会填充到 ModEntry.direct_urls 中，
    供 fetcher 直接使用而无需二次查询 API。

    Args:
        index_path: modrinth.index.json 文件路径。

    Returns:
        Manifest 实例。

    Raises:
        KeyError / ValueError: 清单格式不符合预期。
    """
    with index_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # --- 依赖表：提取 mc 版本与加载器 ---
    deps = data.get("dependencies", [])
    mc_version = ""
    loader_type = LoaderType.VANILLA
    loader_version: str | None = None

    for dep in deps:
        pid = dep.get("projectID", "")
        vid = dep.get("versionId", "")
        if pid == "minecraft":
            mc_version = str(vid)
        elif pid in _MODRINTH_LOADER_MAP:
            loader_type = _MODRINTH_LOADER_MAP[pid]
            loader_version = str(vid) if vid else None

    if not mc_version:
        raise ValueError("Modrinth index 缺少 minecraft 依赖")

    # --- 模组文件列表 ---
    mods: list[ModEntry] = []
    for file_entry in data.get("files", []):
        path = file_entry.get("path", "")
        downloads = file_entry.get("downloads", [])
        hashes = file_entry.get("hashes", {})
        filename = path.split("/")[-1] if "/" in path else path
        mods.append(
            ModEntry(
                source=ModSource.MODRINTH,
                project_id="",  # Modrinth 不要求 project_id 查询
                file_id="",  # 直接带下载地址
                filename=filename or "unknown.jar",
                required=True,
                direct_urls=downloads,
                hashes=hashes,
            )
        )

    return Manifest(
        mc_version=mc_version,
        loader_type=loader_type,
        loader_version=loader_version,
        mods=mods,
        source=ModSource.MODRINTH,
        raw_path=str(index_path),
    )
