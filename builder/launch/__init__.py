"""builder.launch — 启动脚本生成。

根据加载器类型和模组数量自动生成 start.bat / start.sh 启动脚本，
使用 Aikar's Flags 优化 GC，自动分配合理内存。
"""
from .script_gen import generate_launch_scripts

__all__ = ["generate_launch_scripts"]
