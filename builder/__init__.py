"""builder — 模块一·服务端工作目录构建 (Server Workspace Builder)。

将多种用户输入源（引导包 / 完整客户端）全自动编译为开箱即用的服务端工作目录。
入口：builder.pipeline.build_workspace()
"""
from .errors import (
    BuildError,
    EulaRejectedError,
    IntegrityError,
    UnrecognizedPackError,
    ZipSlipError,
)
from .pipeline import build_workspace

__all__ = [
    "build_workspace",
    "BuildError",
    "EulaRejectedError",
    "IntegrityError",
    "UnrecognizedPackError",
    "ZipSlipError",
]
