"""builder.unpack.root_locator — 阶段一·畸形文件树自适应，定位真正的游戏根目录。

玩家压缩客户端时常多包一层"我的整合包"文件夹。本模块深度优先下钻，
直至定位到真正的游戏根目录，严禁直接抛"无效整合包"。
"""
from __future__ import annotations

from pathlib import Path

# 认定为"游戏根"的强信号文件 / 目录名（小写匹配）
_GAME_ROOT_MARKERS = {
    # 引导包清单
    "manifest.json",
    "modrinth.index.json",
    # 完整客户端典型目录
    "mods",
    "config",
    "versions",
    "saves",
    "logs",
    "options.txt",
    # 服务端典型文件
    "server.properties",
    "eula.txt",
}

# 单层下钻的最大深度，防止恶意/畸形目录无限嵌套
_MAX_DEPTH = 5


def _looks_like_game_root(d: Path) -> bool:
    """目录下是否存在任一游戏根标志（文件或目录）。"""
    try:
        names = {child.name.lower() for child in d.iterdir()}
    except (PermissionError, FileNotFoundError):
        return False
    return any(marker in names for marker in _GAME_ROOT_MARKERS)


def locate_game_root(sandbox: Path, max_depth: int = _MAX_DEPTH) -> Path:
    """从沙箱根出发，定位真正的游戏根目录。

    策略：
        1. 若 sandbox 本身即像游戏根，直接返回。
        2. 若一级只有一个子目录，则递归向下探查（最多 max_depth 层），
           在第一个"像游戏根"的目录处停下。
        3. 探查不到任何游戏根 → 抛 ValueError（由 discriminator 进一步判定）。

    Args:
        sandbox: 解压后的沙箱根目录。
        max_depth: 向下探查的最大层数。

    Returns:
        定位到的游戏根目录（绝对路径）。

    Raises:
        ValueError: 超过 max_depth 仍未找到游戏根。
    """
    current = sandbox.resolve()
    if _looks_like_game_root(current):
        return current

    for _ in range(max_depth):
        # 仅当"一级只有一个子目录"时才下钻，避免在多目录中误选
        try:
            children = [c for c in current.iterdir() if c.is_dir()]
        except (PermissionError, FileNotFoundError):
            break
        if len(children) != 1:
            break
        nxt = children[0]
        if _looks_like_game_root(nxt):
            return nxt
        current = nxt

    # 探查到底仍未命中标志，回退返回最深可达目录，交由 discriminator 做最终判定
    return current
