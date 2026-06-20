"""core.contracts.manifest — 整合包元数据契约。

定义引导包（CurseForge / Modrinth）解析后产出的统一 Manifest 结构，
作为 metadata 阶段（生产者）→ fetcher 阶段（消费者）之间的传输契约。
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class LoaderType(str, Enum):
    """模组加载器类型。"""

    VANILLA = "vanilla"
    FORGE = "forge"
    NEOFORGE = "neoforge"
    FABRIC = "fabric"
    QUILT = "quilt"
    PAPER = "paper"  # 服务端仅插件，非模组加载器


class ModSource(str, Enum):
    """模组来源平台。"""

    CURSEFORGE = "curseforge"
    MODRINTH = "modrinth"


class ModEntry(BaseModel):
    """单个模组的下载标识。

    CurseForge 用 (project_id, file_id) 定位；
    Modrinth 文件清单自带 downloads URL，会填到 direct_urls。
    """

    source: ModSource
    project_id: str
    file_id: str
    filename: str
    required: bool = True
    # Modrinth 清单直接给出下载地址，CF 则需查询端点，填充后供 fetcher 直接使用
    direct_urls: list[str] = Field(default_factory=list)
    # 可选哈希校验：{"sha1": "...", "sha512": "..."}
    hashes: dict[str, str] = Field(default_factory=dict)


class Manifest(BaseModel):
    """统一的整合包元数据，喂给 fetcher 进行多源下载。"""

    mc_version: str  # 如 "1.20.1"
    loader_type: LoaderType
    loader_version: Optional[str] = None  # 如 "47.1.3"；VANILLA 为 None
    mods: list[ModEntry] = Field(default_factory=list)
    source: ModSource  # 清单原始来源，决定 fetcher 的 URL 构造策略
    # 原始清单文件路径，便于追溯与二次读取
    raw_path: Optional[str] = None
