"""builder.install.java_probe — Java 运行时探测。

在系统 PATH / JAVA_HOME / 常见安装路径中查找可用的 java 命令。
支持按最低版本要求筛选，优先返回满足版本的 Java。
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Windows 常见 Java 安装路径（包括自定义 SDK 目录）
_WINDOWS_JAVA_PATHS = [
    r"D:\sdks",                       # 用户自定义 SDK 目录
    r"C:\sdks",                       # 备用 SDK 目录
    r"C:\Program Files\Java",
    r"C:\Program Files (x86)\Java",
    r"C:\Program Files\Eclipse Adoptium",
    r"C:\Program Files\Microsoft",
    r"C:\Program Files\Zulu",
    r"C:\Program Files\BellSoft",
]


def find_java(*, min_version: int = 0) -> str | None:
    """探测系统可用的 Java 路径。

    搜索顺序：
        1. 系统 PATH 中的 java
        2. JAVA_HOME 环境变量
        3. Windows 常见安装路径（递归搜索子目录）

    如果指定 min_version，优先返回满足版本要求的 Java；
    若无满足版本要求的，返回最高版本的 Java。

    Args:
        min_version: 最低主版本号（如 21 表示需要 Java 21+）。0 表示不限。

    Returns:
        java 可执行文件路径，未找到返回 None。
    """
    candidates: list[tuple[str, int]] = []  # (path, major_version)

    # 1. 系统 PATH 中的 java
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    for d in path_dirs:
        java_bin = Path(d) / "java.exe" if os.name == "nt" else Path(d) / "java"
        if java_bin.is_file():
            _try_add(java_bin, candidates)
            break

    # 2. JAVA_HOME
    java_home = os.environ.get("JAVA_HOME", "")
    if java_home:
        java_bin = Path(java_home) / "bin" / ("java.exe" if os.name == "nt" else "java")
        if java_bin.is_file():
            _try_add(java_bin, candidates)

    # 3. Windows 常见路径（递归搜索子目录）
    if os.name == "nt":
        for base_dir in _WINDOWS_JAVA_PATHS:
            _scan_java_dir(base_dir, candidates)

    if not candidates:
        logger.warning("未找到 Java 运行时，服务端安装可能失败")
        return None

    # 去重（按 resolve 路径）
    seen: set[Path] = set()
    unique: list[tuple[str, int]] = []
    for path, ver in candidates:
        norm = Path(path).resolve()
        if norm not in seen:
            seen.add(norm)
            unique.append((path, ver))

    # 优先返回满足 min_version 的最低版本（避免过新版本不兼容）
    # MC 官方推荐特定 Java 版本，过新可能有问题
    qualified = [(p, v) for p, v in unique if v >= min_version]
    if qualified:
        qualified.sort(key=lambda x: x[1])  # 升序，选最低满足的
        best = qualified[0]
        logger.info("选择 Java %d: %s", best[1], best[0])
        return best[0]

    # 无满足版本的，返回最高版本
    unique.sort(key=lambda x: x[1], reverse=True)
    best = unique[0]
    if min_version > 0:
        logger.warning(
            "未找到 Java %d+，最高版本为 Java %d: %s",
            min_version, best[1], best[0],
        )
    return best[0]


def check_java_version(java_path: str) -> str | None:
    """检查 Java 版本。

    Returns:
        Java 版本字符串（如 "21.0.2"），检查失败返回 None。
    """
    try:
        result = subprocess.run(
            [java_path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # java -version 输出到 stderr
        output = result.stderr or result.stdout
        # 解析版本号，格式如: java version "21.0.2" 或 openjdk version "21.0.2"
        for line in output.splitlines():
            if "version" in line:
                start = line.find('"')
                end = line.rfind('"')
                if start != -1 and end != -1 and start < end:
                    version = line[start + 1:end]
                    logger.info("Java 版本: %s", version)
                    return version
    except Exception as exc:
        logger.warning("Java 版本检查失败: %s", exc)
    return None


def _parse_major_version(version_str: str) -> int:
    """解析 Java 主版本号。

    Java 8 及之前: 1.8.x → 8
    Java 9+: 9.x, 11.x, 17.x, 21.x → 9, 11, 17, 21
    """
    parts = version_str.split(".")
    if parts[0] == "1" and len(parts) > 1:
        return int(parts[1])  # 1.8 → 8
    return int(parts[0])  # 21.0.2 → 21


def _try_add(java_bin: Path, candidates: list[tuple[str, int]]) -> None:
    """尝试添加一个 Java 候选路径。"""
    ver = check_java_version(str(java_bin))
    if ver:
        major = _parse_major_version(ver)
        candidates.append((str(java_bin), major))
    else:
        candidates.append((str(java_bin), 0))


def _scan_java_dir(base_dir: str, candidates: list[tuple[str, int]]) -> None:
    """递归扫描目录查找 java 可执行文件（支持多级嵌套）。"""
    base = Path(base_dir)
    if not base.is_dir():
        return
    try:
        entries = list(base.iterdir())
    except PermissionError:
        return

    for entry in entries:
        if entry.is_file() and entry.name == "java.exe":
            _try_add(entry, candidates)
        elif entry.is_dir():
            _scan_java_dir_recursive(str(entry), candidates, depth=3)


def _scan_java_dir_recursive(dir_path: str, candidates: list[tuple[str, int]], depth: int) -> None:
    """递归搜索子目录查找 java.exe。"""
    if depth <= 0:
        return
    d = Path(dir_path)
    try:
        for entry in d.iterdir():
            if entry.is_file() and entry.name == "java.exe":
                _try_add(entry, candidates)
            elif entry.is_dir() and "bin" in entry.name.lower():
                java_bin = entry / "java.exe"
                if java_bin.is_file():
                    _try_add(java_bin, candidates)
            elif entry.is_dir():
                _scan_java_dir_recursive(str(entry), candidates, depth - 1)
    except PermissionError:
        pass
