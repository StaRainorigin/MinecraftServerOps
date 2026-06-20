"""builder.install — 阶段五·服务端安装。

执行 Forge/NeoForge/Fabric 安装器，将 loader 注入服务端目录。
"""
from .installer import install_server

__all__ = ["install_server"]
