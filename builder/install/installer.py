"""builder.install.installer — 阶段五·服务端安装器执行。

执行 Forge/NeoForge/Fabric 安装器，将 loader 注入服务端目录。
安装器会自动下载 Minecraft 服务端 jar 和 loader 库文件。
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from core.contracts import LoaderType, Manifest

from .java_probe import check_java_version, find_java

logger = logging.getLogger(__name__)


def install_server(workspace: Path, manifest: Manifest) -> bool:
    """在服务端目录中执行 loader 安装器。

    对于 NeoForge/Forge：执行 installer.jar --installServer
    对于 Fabric：执行 fabric-installer.jar server
    对于 Vanilla：无需安装（服务端 jar 已在下载阶段获取）

    Args:
        workspace: 服务端工作目录。
        manifest: 整合包元数据。

    Returns:
        True 安装成功，False 安装失败。
    """
    loader = manifest.loader_type

    if loader in (LoaderType.VANILLA, LoaderType.PAPER):
        logger.info("原版/Paper 无需安装器，跳过")
        return True

    # 探测 Java（MC 1.21+ 需要 Java 21+）
    mc_parts = manifest.mc_version.split(".")
    mc_minor = int(mc_parts[1]) if len(mc_parts) > 1 else 0
    min_java = 21 if mc_minor >= 21 else 17

    java_path = find_java(min_version=min_java)
    if not java_path:
        logger.error("未找到 Java，无法执行安装器")
        return False

    # 再次确认版本
    java_version = check_java_version(java_path)
    if java_version:
        major = _parse_major_version(java_version)
        if mc_minor >= 21 and major < 21:
            logger.error(
                "MC 1.21+ 需要 Java 21+，当前 Java 版本: %s (major=%d)",
                java_version, major,
            )
            return False

    # 查找安装器 jar
    installer_jar = _find_installer(workspace, manifest)
    if not installer_jar:
        logger.warning("未找到安装器 jar，跳过安装（可能需要手动安装）")
        return False

    # 预下载安装器可能需要的 Maven 库（中国网络 maven.neoforged.net 连接困难）
    if loader == LoaderType.NEOFORGE:
        _prefetch_neoforge_universal(workspace, manifest)

    # 执行安装
    logger.info("执行安装器: %s", installer_jar.name)
    success = _run_installer(java_path, installer_jar, workspace, manifest)

    if success:
        # 安装成功后删除安装器 jar（节省空间）
        try:
            installer_jar.unlink()
            # 也删除安装器的 .log 文件
            log_file = installer_jar.with_suffix(".log")
            if log_file.exists():
                log_file.unlink()
            logger.info("已清理安装器文件")
        except OSError:
            pass

    return success


def _find_installer(workspace: Path, manifest: Manifest) -> Path | None:
    """在工作目录中查找安装器 jar 文件。"""
    loader_ver = manifest.loader_version or "unknown"
    # 优先查找 downloader 保存的标准文件名
    standard_name = f"{manifest.loader_type.value}-{loader_ver}-installer.jar"
    candidate = workspace / standard_name
    if candidate.is_file():
        return candidate

    # 降级：查找任何 installer.jar
    for jar in workspace.iterdir():
        if jar.is_file() and jar.suffix.lower() == ".jar":
            name_lower = jar.name.lower()
            if "installer" in name_lower:
                return jar

    # 再查找子目录
    for subdir in workspace.iterdir():
        if subdir.is_dir():
            for jar in subdir.iterdir():
                if jar.is_file() and jar.suffix.lower() == ".jar":
                    if "installer" in jar.name.lower():
                        return jar

    return None


def _run_installer(
    java_path: str,
    installer_jar: Path,
    workspace: Path,
    manifest: Manifest,
) -> bool:
    """执行安装器进程。"""
    loader = manifest.loader_type

    if loader == LoaderType.NEOFORGE:
        cmd = [java_path, "-jar", str(installer_jar), "--installServer"]
    elif loader == LoaderType.FORGE:
        cmd = [java_path, "-jar", str(installer_jar), "--installServer"]
    elif loader == LoaderType.FABRIC:
        cmd = [java_path, "-jar", str(installer_jar), "server", "-dir", str(workspace)]
    elif loader == LoaderType.QUILT:
        cmd = [java_path, "-jar", str(installer_jar), "server", "-dir", str(workspace)]
    else:
        logger.warning("不支持的加载器类型: %s", loader.value)
        return False

    logger.info("安装命令: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=600,  # 10 分钟超时
        )

        if result.returncode == 0:
            logger.info("安装器执行成功")
            return True
        else:
            logger.error("安装器执行失败 (exit code %d)", result.returncode)
            # 输出关键日志
            if result.stdout:
                for line in result.stdout.splitlines()[-10:]:
                    logger.error("  stdout: %s", line)
            if result.stderr:
                for line in result.stderr.splitlines()[-10:]:
                    logger.error("  stderr: %s", line)
            return False

    except subprocess.TimeoutExpired:
        logger.error("安装器执行超时（10分钟）")
        return False
    except Exception as exc:
        logger.error("安装器执行异常: %s", exc)
        return False


def _parse_major_version(version_str: str) -> int:
    """解析 Java 主版本号。

    Java 8 及之前: 1.8.x → 8
    Java 9+: 9.x, 11.x, 17.x, 21.x → 9, 11, 17, 21
    """
    parts = version_str.split(".")
    if parts[0] == "1" and len(parts) > 1:
        return int(parts[1])  # 1.8 → 8
    return int(parts[0])  # 21.0.2 → 21


def _prefetch_neoforge_universal(workspace: Path, manifest: Manifest) -> None:
    """预下载 NeoForge universal jar 到 libraries 目录。

    NeoForge 安装器需要从 maven.neoforged.net 下载 universal jar，
    但在中国网络环境下该域名经常连接重置。提前通过 BMCLAPI 镜像下载
    可以避免安装器失败。

    安装器会检查 libraries 目录下已有的文件，如果 checksum 合法则跳过下载。
    """
    loader_version = manifest.loader_version
    if not loader_version:
        return

    dest = workspace / "libraries" / "net" / "neoforged" / "neoforge" / loader_version / f"neoforge-{loader_version}-universal.jar"

    # 如果已经存在则跳过
    if dest.is_file() and dest.stat().st_size > 0:
        logger.info("NeoForge universal jar 已存在，跳过预下载: %s", dest.name)
        return

    dest.parent.mkdir(parents=True, exist_ok=True)

    urls = [
        f"https://bmclapi2.bangbang93.com/maven/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}-universal.jar",
        f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}-universal.jar",
    ]

    import httpx

    for url in urls:
        logger.info("预下载 NeoForge universal jar: %s", url)
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=120) as resp:
                if resp.status_code == 200:
                    with open(dest, "wb") as f:
                        for chunk in resp.iter_bytes(65536):
                            f.write(chunk)
                    logger.info(
                        "预下载完成: %s (%.1f MB)",
                        dest.name, dest.stat().st_size / 1024 / 1024,
                    )
                    return
                else:
                    logger.warning("预下载失败: status=%d", resp.status_code)
        except Exception as exc:
            logger.warning("预下载异常: %s", exc)

    logger.warning("NeoForge universal jar 预下载失败，安装器可能会因网络问题失败")
