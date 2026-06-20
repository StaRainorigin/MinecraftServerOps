"""builder.unpack.discriminator — 阶段一·输入模式自动判别。

根据 game_root 的目录特征自动切换处理分支：
    - 存在标准清单文件 → 引导包模式（BOOTSTRAP）
    - 存在 mods/ 且含 .jar，或根/一级有大量 .jar → 完整客户端模式（CLIENT）
    - 否则抛 UnrecognizedPackError
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from core.contracts import InputMode

from ..errors import UnrecognizedPackError

# 引导包标准清单文件名（小写匹配）
_BOOTSTRAP_MANIFESTS = ("manifest.json", "modrinth.index.json")

# manifest.json 中判定为 CurseForge 引导包的关键字段
_CF_HINT_KEYS = ("manifestType", "manifestVersion", "minecraft", "files")

# modrinth.index.json 中判定为 Modrinth 引导包的关键字段
_MODRINTH_HINT_KEYS = ("format", "game", "versionId")


def _is_bootstrap_manifest(path: Path) -> bool:
    """检查单个清单文件是否真的是引导包索引（而非同名无关文件）。"""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False

    if not isinstance(data, dict):
        return False

    if path.name.lower() == "manifest.json":
        return any(k in data for k in _CF_HINT_KEYS)
    if path.name.lower() == "modrinth.index.json":
        return any(k in data for k in _MODRINTH_HINT_KEYS)
    return False


def find_manifest(game_root: Path) -> Optional[Path]:
    """在游戏根下寻找有效的引导包清单文件，找到返回路径，否则 None。"""
    for name in _BOOTSTRAP_MANIFESTS:
        candidate = game_root / name
        if candidate.is_file() and _is_bootstrap_manifest(candidate):
            return candidate
    return None


def _count_jars(d: Path) -> int:
    """统计目录下（含一级子目录）的 .jar 文件数。"""
    count = 0
    try:
        for child in d.iterdir():
            if child.is_file() and child.suffix.lower() == ".jar":
                count += 1
            elif child.is_dir() and child.name.lower() == "mods":
                count += sum(
                    1
                    for m in child.iterdir()
                    if m.is_file() and m.suffix.lower() == ".jar"
                )
    except (PermissionError, FileNotFoundError):
        pass
    return count


def discriminate(game_root: Path) -> InputMode:
    """判别输入模式。

    判别优先级：
        1. 存在有效引导包清单 → BOOTSTRAP
        2. 存在 mods/ 且含 .jar，或根目录有大量 .jar → CLIENT
        3. 均不匹配 → 抛 UnrecognizedPackError

    Returns:
        InputMode.BOOTSTRAP 或 InputMode.CLIENT。

    Raises:
        UnrecognizedPackError: 无法识别为任一模式。
    """
    # 优先判定引导包：清单文件是最强的信号
    manifest = find_manifest(game_root)
    if manifest is not None:
        return InputMode.BOOTSTRAP

    # 其次判定完整客户端：以 jar 实体数量为依据
    if _count_jars(game_root) > 0:
        return InputMode.CLIENT

    raise UnrecognizedPackError(
        f"无法识别输入模式：{game_root} 下既无引导包清单，也无 .jar 实体。"
        "（模式 C 自然语言需求本阶段待定）"
    )
