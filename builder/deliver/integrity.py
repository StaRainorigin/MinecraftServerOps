"""builder.deliver.integrity — 阶段五·资产封账完整性校验。

在交付前确保 Java 核心存在、EULA 已签署、Mod 文件非空。
校验不通过则拒绝交付，列出具体问题供上层处理。
"""
from __future__ import annotations

import logging
from pathlib import Path

from core.contracts import InputMode, IntegrityReport

logger = logging.getLogger(__name__)


def verify_integrity(workspace: Path, mode: InputMode) -> IntegrityReport:
    """对工作目录进行完整性校验。

    校验项：
        1. EULA：eula.txt 存在且包含 eula=true
        2. 服务端核心：根目录或一级子目录下存在可执行 .jar
        3. Mods 完整性：mods/ 下无 0 字节 .jar 文件

    Args:
        workspace: 待校验的工作目录。
        mode: 输入模式（引导包 / 客户端，影响校验严格程度）。

    Returns:
        IntegrityReport（ok=True 通过，issues 列出问题）。
    """
    issues: list[str] = []

    # ── 1. EULA 校验 ──
    eula_file = workspace / "eula.txt"
    if not eula_file.is_file():
        issues.append("eula.txt 不存在")
    else:
        try:
            content = eula_file.read_text(encoding="utf-8")
            if "eula=true" not in content:
                issues.append("eula.txt 未同意（缺少 eula=true）")
        except OSError as exc:
            issues.append(f"eula.txt 读取失败: {exc}")

    # ── 2. 服务端核心校验 ──
    has_core = False
    for jar in _iter_root_jars(workspace):
        if jar.stat().st_size > 0:
            has_core = True
            break
    if not has_core and mode == InputMode.BOOTSTRAP:
        # 引导包模式必须有核心；客户端模式可能已自带
        issues.append("未找到有效的服务端核心 .jar")

    # ── 3. Mods 完整性 ──
    mods_dir = workspace / "mods"
    if mods_dir.is_dir():
        for jar in mods_dir.iterdir():
            if jar.is_file() and jar.suffix.lower() == ".jar":
                if jar.stat().st_size == 0:
                    issues.append(f"空文件: mods/{jar.name}")

    ok = len(issues) == 0
    if ok:
        logger.info("完整性校验通过: %s", workspace)
    else:
        logger.warning("完整性校验未通过 (%d 项问题): %s", len(issues), workspace)
        for issue in issues:
            logger.warning("  - %s", issue)

    return IntegrityReport(ok=ok, issues=issues)


def _iter_root_jars(workspace: Path) -> list[Path]:
    """列出工作目录根及一级子目录下的 .jar 文件。"""
    jars: list[Path] = []
    try:
        for item in workspace.iterdir():
            if item.is_file() and item.suffix.lower() == ".jar":
                jars.append(item)
            elif item.is_dir():
                for child in item.iterdir():
                    if child.is_file() and child.suffix.lower() == ".jar":
                        jars.append(child)
    except (PermissionError, FileNotFoundError):
        pass
    return jars
