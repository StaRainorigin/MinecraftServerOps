"""builder.launch.script_gen — 阶段六·启动脚本生成。

根据加载器类型和模组数量自动生成 start.bat / start.sh 启动脚本。
使用 Aikar's Flags 优化 GC，自动分配合理内存。
自动检测 Java 21+ 路径并写入脚本。
"""
from __future__ import annotations

import logging
from pathlib import Path

from core.contracts import LoaderType, Manifest

logger = logging.getLogger(__name__)


def generate_launch_scripts(workspace: Path, manifest: Manifest | None = None) -> list[Path]:
    """生成启动脚本。

    Args:
        workspace: 服务端工作目录。
        manifest: 整合包元数据（用于判断加载器类型和模组数）。

    Returns:
        生成的脚本文件路径列表。
    """
    loader_type = manifest.loader_type if manifest else LoaderType.VANILLA
    loader_version = manifest.loader_version if manifest else None
    mc_version = manifest.mc_version if manifest else "1.21"
    mod_count = len(manifest.mods) if manifest else 0

    # 计算推荐内存
    memory_mb = _recommend_memory(mod_count)
    memory_str = f"{memory_mb}M"

    # 获取启动类路径
    launch_cmd = _build_launch_command(workspace, loader_type, loader_version)

    # 生成 Aikar's Flags
    jvm_flags = _aikars_flags(memory_mb)

    # 检测 Java 路径（MC 1.21+ 需要 Java 21+）
    mc_parts = mc_version.split(".")
    mc_minor = int(mc_parts[1]) if len(mc_parts) > 1 else 0
    min_java = 21 if mc_minor >= 21 else 17

    # .bat 用检测到的 Windows 路径，.sh 用 "java"（Linux 部署环境不同）
    java_cmd_win = _detect_java_cmd(min_java)
    java_cmd_unix = "java"

    generated: list[Path] = []

    # start.bat (Windows)
    bat_content = _render_bat(jvm_flags, memory_str, launch_cmd, java_cmd_win)
    bat_path = workspace / "start.bat"
    bat_path.write_text(bat_content, encoding="utf-8")
    generated.append(bat_path)

    # start.sh (Linux/Mac)
    sh_content = _render_sh(jvm_flags, memory_str, launch_cmd, java_cmd_unix)
    sh_path = workspace / "start.sh"
    sh_path.write_text(sh_content, encoding="utf-8")
    generated.append(sh_path)

    logger.info("启动脚本已生成: %s（推荐内存=%s, 模组数=%d, Java(win)=%s）",
                ", ".join(p.name for p in generated), memory_str, mod_count, java_cmd_win)

    return generated


def _detect_java_cmd(min_version: int) -> str:
    """检测 Java 可执行路径。

    优先找到满足版本要求的 Java，返回路径；
    如果找不到则返回 "java"（依赖用户自行配置）。
    """
    try:
        from builder.install.java_probe import find_java
        java_path = find_java(min_version=min_version)
        if java_path:
            # Windows 路径含空格需要引号
            if " " in java_path:
                return f'"{java_path}"'
            return java_path
    except Exception:
        pass
    return "java"


def _recommend_memory(mod_count: int) -> int:
    """根据模组数量推荐内存（MB）。

    策略：基础 4GB，每 100 个模组 +1GB，上限 12GB，下限 2GB。
    """
    base = 4096
    extra = (mod_count // 100) * 1024
    total = min(base + extra, 12288)
    total = max(total, 2048)
    return total


def _build_launch_command(workspace: Path, loader_type: LoaderType, loader_version: str | None) -> str:
    """构建服务端启动命令。

    NeoForge 1.21+ 使用 @libraries/.../args 方式启动。
    """
    if loader_type == LoaderType.NEOFORGE and loader_version:
        # NeoForge 1.21+ 启动方式
        # 查找 libraries 目录下的 args 文件
        args_file = _find_neoforge_args(workspace, loader_version)
        if args_file:
            return f"@{args_file}"

        # 降级：查找 neoforge-{ver}-universal.jar 或 run.jar
        for candidate_name in [
            f"neoforge-{loader_version}-universal.jar",
            f"neoforge-{loader_version}.jar",
            "run.jar",
        ]:
            candidate = workspace / candidate_name
            if candidate.is_file():
                return f"-jar {candidate_name}"

        # 再降级：查找 libraries 下的 universal jar
        libs_dir = workspace / "libraries"
        if libs_dir.is_dir():
            for jar in libs_dir.rglob("neoforge*universal*.jar"):
                rel = jar.relative_to(workspace).as_posix()
                return f"-jar {rel}"

        # 最终降级：如果安装器还没运行，生成占位命令
        # 安装器运行后会创建 @libraries 路径
        return f"@libraries/net/neoforged/neoforge/{loader_version}/win_args.txt"

    elif loader_type == LoaderType.FORGE and loader_version:
        # Forge 启动方式
        for candidate_name in [
            f"forge-{loader_version}-universal.jar",
            f"forge-{loader_version}.jar",
            "run.jar",
        ]:
            candidate = workspace / candidate_name
            if candidate.is_file():
                return f"-jar {candidate_name}"

    elif loader_type == LoaderType.FABRIC:
        for candidate_name in ["fabric-server-launch.jar", "fabric-server-launcher.jar"]:
            candidate = workspace / candidate_name
            if candidate.is_file():
                return f"-jar {candidate_name}"

    elif loader_type == LoaderType.QUILT:
        for candidate_name in ["quilt-server-launch.jar"]:
            candidate = workspace / candidate_name
            if candidate.is_file():
                return f"-jar {candidate_name}"

    # 降级：查找任何 server-launch / run / minecraft_server jar
    for jar in workspace.iterdir():
        if jar.is_file() and jar.suffix.lower() == ".jar":
            name_lower = jar.name.lower()
            if any(kw in name_lower for kw in ("server", "launch", "run", "minecraft")):
                return f"-jar {jar.name}"

    # 最终降级：占位
    return "-jar server.jar"


def _find_neoforge_args(workspace: Path, loader_version: str) -> str | None:
    """查找 NeoForge 的 @args 文件。"""
    libs_dir = workspace / "libraries"
    if not libs_dir.is_dir():
        return None

    # NeoForge 安装后生成的 args 文件路径：
    # libraries/net/neoforged/neoforge/{ver}/win_args.txt
    for name in ["win_args.txt", "unix_args.txt", f"neoforge_{loader_version}_server_args.txt"]:
        for f in libs_dir.rglob(name):
            # 使用正斜杠，兼容 Windows (@args) 和 Linux
            rel = f.relative_to(workspace).as_posix()
            return rel

    return None


def _aikars_flags(memory_mb: int) -> list[str]:
    """生成 Aikar's Flags（GC 优化参数）。

    根据内存大小调整 G1 Region Size。
    """
    if memory_mb >= 12288:
        region_size = "32M"
    elif memory_mb >= 8192:
        region_size = "16M"
    else:
        region_size = "8M"

    return [
        "-XX:+UseG1GC",
        "-XX:+ParallelRefProcEnabled",
        "-XX:MaxGCPauseMillis=200",
        "-XX:+UnlockExperimentalVMOptions",
        "-XX:+DisableExplicitGC",
        "-XX:+AlwaysPreTouch",
        "-XX:G1NewSizePercent=30",
        "-XX:G1MaxNewSizePercent=40",
        f"-XX:G1HeapRegionSize={region_size}",
        "-XX:G1ReservePercent=20",
        "-XX:G1HeapWastePercent=5",
        "-XX:G1MixedGCCountTarget=4",
        "-XX:InitiatingHeapOccupancyPercent=15",
        "-XX:G1MixedGCLiveThresholdPercent=90",
        "-XX:G1RSetUpdatingPauseTimePercent=5",
        "-XX:SurvivorRatio=32",
        "-XX:+PerfDisableSharedMem",
        "-XX:MaxTenuringThreshold=1",
        "-Dusing.aikars.flags=https://mcflags.emc.gs",
        "-Daikars.new.flags=true",
    ]


def _render_bat(flags: list[str], memory: str, launch_cmd: str, java_cmd: str) -> str:
    """渲染 Windows 批处理脚本。"""
    flags_str = " ".join(flags)
    return f"""@echo off
REM MC-SRE 自动生成的服务端启动脚本
REM 推荐内存: {memory}

{java_cmd} -Xms{memory} -Xmx{memory} {flags_str} {launch_cmd} nogui
pause
"""


def _render_sh(flags: list[str], memory: str, launch_cmd: str, java_cmd: str) -> str:
    """渲染 Linux/Mac shell 脚本。"""
    flags_str = " ".join(flags)
    # Linux 下用 unix_args.txt 而非 win_args.txt
    if "win_args.txt" in launch_cmd:
        launch_cmd = launch_cmd.replace("win_args.txt", "unix_args.txt")
    return f"""#!/bin/bash
# MC-SRE 自动生成的服务端启动脚本
# 推荐内存: {memory}
# 请确保 Java 21+ 已安装并在 PATH 中（或修改下方 JAVA_CMD 变量）

JAVA_CMD="{java_cmd}"

$JAVA_CMD -Xms{memory} -Xmx{memory} {flags_str} {launch_cmd} nogui
"""
