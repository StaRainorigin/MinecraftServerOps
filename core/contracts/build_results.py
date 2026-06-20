"""core.contracts.build_results — 流水线各阶段的结果与最终交付契约。

承载 builder 五个阶段之间流转的结构化结果，以及最终交付给上层
（orchestrator / 用户）的 BuildResult。
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .manifest import Manifest, ModEntry


class InputMode(str, Enum):
    """输入模式（对应 PRD 多态输入）。"""

    BOOTSTRAP = "bootstrap"  # 模式 A：轻量引导包（仅元数据）
    CLIENT = "client"  # 模式 B：厚重客户端（含 mods/*.jar）
    NATURAL = "natural"  # 模式 C：自然语言需求（本阶段待定）


class EulaDecision(str, Enum):
    """EULA 交互闸的用户决定。"""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class UnpackResult(BaseModel):
    """阶段一产物：解包 + 根定位 + 模式判别的结果。"""

    sandbox_root: Path
    mode: InputMode
    game_root: Path  # 定位到的真正游戏根目录
    # 引导包模式下的清单文件路径；客户端模式为 None
    manifest_path: Optional[Path] = None


class MissingMod(BaseModel):
    """全网断流降级记录：某 Mod 在所有源都拉取失败。"""

    entry: ModEntry
    reason: str
    tried_sources: list[str] = Field(default_factory=list)


class DownloadReport(BaseModel):
    """阶段三产物：fetcher 下载结果。"""

    succeeded: list[ModEntry] = Field(default_factory=list)
    missing: list[MissingMod] = Field(default_factory=list)
    # 下载的服务端核心 .jar（如服务端 jar / 加载器 installer 产物）
    server_artifacts: list[Path] = Field(default_factory=list)


class IntegrityReport(BaseModel):
    """阶段五前置：完整性校验结果。"""

    ok: bool
    issues: list[str] = Field(default_factory=list)


class BuildResult(BaseModel):
    """最终交付：交付给 orchestrator / 用户的工作目录信息。"""

    workspace_path: Path
    total_size_bytes: int
    mod_count: int
    mode: InputMode
    missing: list[MissingMod] = Field(default_factory=list)
    # 透传便于上层复用
    manifest: Optional[Manifest] = None
