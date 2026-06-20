"""builder.metadata.curseforge — 阶段二·解析 CurseForge manifest.json 索引。

CurseForge 导出的 manifest.json 典型结构：
{
  "minecraft": { "version": "1.20.1", "modLoaders": [{"id": "forge-47.1.3", "primary": true}] },
  "files": [{ "projectID": 238222, "fileID": 5128832, "required": true }, ...]
}

注意：CF manifest 不含真实文件名，需通过 cf_resolver 异步解析后填充。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from core.contracts import LoaderType, Manifest, ModEntry, ModSource

logger = logging.getLogger(__name__)


# 加载器 ID 前缀 → LoaderType 映射
_LOADER_PREFIX_MAP: dict[str, LoaderType] = {
    "forge-": LoaderType.FORGE,
    "neoforge-": LoaderType.NEOFORGE,
    "fabric-": LoaderType.FABRIC,
    "quilt-": LoaderType.QUILT,
}


def _parse_loader_id(raw: str) -> tuple[LoaderType, str | None]:
    """解析加载器 ID 字符串（如 "forge-47.1.3"）→ (LoaderType, 版本号)。

    Returns:
        (LoaderType, version)。无法识别的加载器返回 (LoaderType.VANILLA, None)。
    """
    for prefix, loader in _LOADER_PREFIX_MAP.items():
        if raw.startswith(prefix):
            version = raw[len(prefix) :] or None
            return loader, version
    return LoaderType.VANILLA, None


def parse_curseforge(
    manifest_path: Path,
    *,
    resolved_names: dict[str, tuple[str, str]] | None = None,
) -> Manifest:
    """解析 CurseForge manifest.json，产出统一的 Manifest。

    Args:
        manifest_path: manifest.json 文件路径。
        resolved_names: 可选的 CF 文件名解析结果。
            key = "{project_id}:{file_id}",
            value = (真实文件名, CDN 下载 URL)。
            未提供时使用占位文件名。

    Returns:
        Manifest 实例。

    Raises:
        KeyError / ValueError: 清单格式不符合预期。
    """
    with manifest_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # --- 游戏版本 ---
    mc_block = data.get("minecraft", {})
    mc_version = str(mc_block.get("version", ""))
    if not mc_version:
        raise ValueError("CurseForge manifest 缺少 minecraft.version 字段")

    # --- 加载器（取 primary，无则取第一个） ---
    mod_loaders = mc_block.get("modLoaders", [])
    loader_type = LoaderType.VANILLA
    loader_version: str | None = None
    for ml in mod_loaders:
        lid = ml.get("id", "")
        loader_type, loader_version = _parse_loader_id(lid)
        if loader_type != LoaderType.VANILLA:
            break  # 优先取 primary

    # --- 模组列表 ---
    names = resolved_names or {}
    mods: list[ModEntry] = []
    resolved_count = 0
    for file_entry in data.get("files", []):
        project_id = str(file_entry.get("projectID", ""))
        file_id = str(file_entry.get("fileID", ""))
        required = file_entry.get("required", True)

        key = f"{project_id}:{file_id}"
        real_filename, cdn_url = names.get(key, (None, None))

        # 降级：无解析结果时使用占位文件名
        filename = real_filename or f"{project_id}-{file_id}.jar"
        direct_urls: list[str] = [cdn_url] if cdn_url else []

        if real_filename:
            resolved_count += 1

        mods.append(
            ModEntry(
                source=ModSource.CURSEFORGE,
                project_id=project_id,
                file_id=file_id,
                filename=filename,
                required=bool(required),
                direct_urls=direct_urls,
            )
        )

    logger.info(
        "CurseForge 清单解析完成：%d 个模组，%d 个已解析真实文件名，%d 个使用占位名",
        len(mods), resolved_count, len(mods) - resolved_count,
    )

    return Manifest(
        mc_version=mc_version,
        loader_type=loader_type,
        loader_version=loader_version,
        mods=mods,
        source=ModSource.CURSEFORGE,
        raw_path=str(manifest_path),
    )
