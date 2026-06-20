"""core.contracts — 跨模块数据契约的统一导出口。

集中定义四大模块之间流转的结构化数据契约。所有模块间通信必须使用此处的类型，
确保接口先于实现冻结。
"""
from __future__ import annotations

from .build_results import (
    BuildResult,
    DownloadReport,
    EulaDecision,
    InputMode,
    IntegrityReport,
    MissingMod,
    UnpackResult,
)
from .manifest import LoaderType, Manifest, ModEntry, ModSource

__all__ = [
    # manifest
    "LoaderType",
    "Manifest",
    "ModEntry",
    "ModSource",
    # build_results
    "BuildResult",
    "DownloadReport",
    "EulaDecision",
    "InputMode",
    "IntegrityReport",
    "MissingMod",
    "UnpackResult",
]
