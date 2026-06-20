"""builder.fetcher.sources — 阶段三·多源下载定义。

借鉴 PCL / HMCL 架构，定义官方源 + 国内镜像源的优先级列表。
所有源按优先级排序，fetcher 逐源尝试，成功即停。

CF CDN URL 格式（来自 HMCL 源码）：
    https://edge.forgecdn.net/files/{fileID/1000}/{fileID%1000}/{filename}
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from core.contracts import LoaderType, Manifest, ModEntry, ModSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownloadSource:
    """单个下载源定义。"""

    name: str  # 人类可读名称（日志输出用）
    base_url: str  # 基础 URL
    priority: int  # 数字越小优先级越高


# ──────────────────────────── 内置源列表 ────────────────────────────

# BMCLAPI 镜像（国内高可用，覆盖 Mojang 核心 / Forge / NeoForge 等）
BMCLAPI = DownloadSource(name="BMCLAPI", base_url="https://bmclapi2.bangbang93.com", priority=0)

# Mojang 官方（核心 & Forge maven）
MOJANG_OFFICIAL = DownloadSource(name="Mojang Official", base_url="https://piston-meta.mojang.com", priority=10)

# MCIMirror — PCL2 使用的国内 CF 镜像（将 forgecdn.net 替换为 mod.mcimirror.top）
# 参考 PCL2 ModDownload.vb 的 URL 重写表：*.forgecdn.net → mod.mcimirror.top
MCIMIRROR = DownloadSource(
    name="MCIMirror (PCL2 风格)",
    base_url="https://mod.mcimirror.top",
    priority=15,
)

# CurseForge CDN — edge（API 返回的原始 URL，可能带 ?api-key）
CURSEFORGE_EDGE = DownloadSource(
    name="CurseForge Edge CDN",
    base_url="https://edge.forgecdn.net",
    priority=20,
)

# CurseForge CDN — mediafilez（edge 302 的落地域，直连无 302）
CURSEFORGE_MEDIA = DownloadSource(
    name="CurseForge Media CDN",
    base_url="https://mediafilez.forgecdn.net",
    priority=21,
)

# Modrinth CDN
MODRINTH_CDN = DownloadSource(name="Modrinth CDN", base_url="https://cdn.modrinth.com", priority=20)


# ──────────────────────────── URL 构造 ────────────────────────────


def _cf_cdn_path(file_id: str, filename: str) -> str:
    """构造 CurseForge CDN 的路径部分。

    格式：/files/{fileID//1000}/{fileID%1000}/{filename}
    例：fileID=7471280 → /files/7471/280/xxx.jar

    Args:
        file_id: CurseForge fileID（数字字符串）。
        filename: 真实文件名。

    Returns:
        CDN URL 路径。
    """
    fid_int = int(file_id)
    return f"/files/{fid_int // 1000}/{fid_int % 1000}/{filename}"


def _rewrite_to_mirror(url: str) -> str | None:
    """将 CF CDN URL 重写为 MCIMirror 国内镜像 URL。

    参考 PCL2 ModDownload.vb DlSourceModGet() line 1302-1311：
      edge.forgecdn.net    → mod.mcimirror.top
      mediafilez.forgecdn.net → mod.mcimirror.top
      media.forgecdn.net   → mod.mcimirror.top

    Args:
        url: 原始 CDN URL。

    Returns:
        重写后的镜像 URL，若非 CF CDN 则返回 None。
    """
    for cdn_host in ("edge.forgecdn.net", "mediafilez.forgecdn.net", "media.forgecdn.net"):
        if cdn_host in url:
            return url.replace(cdn_host, "mod.mcimirror.top")
    return None


def build_mod_urls(entry: ModEntry, _manifest: Manifest | None = None) -> list[str]:
    """根据模组条目构造按优先级排列的候选下载 URL 列表。

    优先级策略（参考 PCL2 DlSourceOrder + DlSourceModGet）：
        1. MCIMirror 国内镜像（PCL2 风格，国内优先）
        2. direct_urls（cf_resolver 已填充的真实 CDN URL）
        3. edge.forgecdn.net（HMCL 使用的主 CDN，需真实文件名）
        4. mediafilez.forgecdn.net（备用 CDN）

    去重：同一 URL 只出现一次。

    Args:
        entry: 模组条目。
        _manifest: 所属清单（备用，暂未用到）。

    Returns:
        候选 URL 列表（优先级从高到低）。
    """
    urls: list[str] = []
    seen: set[str] = set()

    def _add(url: str) -> None:
        """去重添加 URL。"""
        if url not in seen:
            seen.add(url)
            urls.append(url)

    if entry.source == ModSource.CURSEFORGE:
        # ── CurseForge：mcimirror 优先，然后 direct_urls，再补 edge/mediafilez ──
        if entry.project_id and entry.file_id:
            is_placeholder = entry.filename == f"{entry.project_id}-{entry.file_id}.jar"
            if not is_placeholder:
                cdn_path = _cf_cdn_path(entry.file_id, entry.filename)
                # 1. MCIMirror 国内镜像（PCL2 风格，国内优先）
                _add(f"{MCIMIRROR.base_url}{cdn_path}")

        # 2. direct_urls（cf_resolver 填充的 mediafilez/edge URL）
        #    同时对 direct_urls 中的 CDN URL 生成 mcimirror 候选（可能上面已加过，去重处理）
        for du in entry.direct_urls:
            mirror = _rewrite_to_mirror(du)
            if mirror:
                _add(mirror)
            _add(du)

        # 3. 补充 edge / mediafilez（如果 direct_urls 没覆盖）
        if entry.project_id and entry.file_id:
            is_placeholder = entry.filename == f"{entry.project_id}-{entry.file_id}.jar"
            if not is_placeholder:
                cdn_path = _cf_cdn_path(entry.file_id, entry.filename)
                _add(f"{CURSEFORGE_EDGE.base_url}{cdn_path}")
                _add(f"{CURSEFORGE_MEDIA.base_url}{cdn_path}")

    elif entry.source == ModSource.MODRINTH:
        # Modrinth：direct_urls 优先，mcimirror 重写
        for du in entry.direct_urls:
            mirror = _rewrite_to_mirror(du)
            if mirror:
                _add(mirror)
            _add(du)

    return urls


async def resolve_neoforge_installer_url(mc_version: str, loader_version: str) -> list[str]:
    """动态获取 NeoForge 安装器下载 URL。

    通过 BMCLAPI 版本 API 获取 installerPath，再拼接完整 URL。

    Args:
        mc_version: Minecraft 版本（如 "1.21.1"）。
        loader_version: NeoForge 版本（如 "21.1.228"）。

    Returns:
        候选 URL 列表。
    """
    urls: list[str] = []

    # 通过 BMCLAPI 获取 installerPath
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(
                f"{BMCLAPI.base_url}/neoforge/version/{loader_version}"
            )
            if r.status_code == 200:
                data = r.json()
                installer_path = data.get("installerPath", "")
                if installer_path:
                    # BMCLAPI 镜像
                    urls.append(f"{BMCLAPI.base_url}{installer_path}")
                    # 官方 maven
                    urls.append(f"https://maven.neoforged.net/releases{installer_path}")
                    logger.info(
                        "NeoForge 安装器路径已解析: %s", installer_path,
                    )
                    return urls
    except Exception as exc:
        logger.warning("BMCLAPI NeoForge 版本查询失败: %s", exc)

    # 降级：使用静态 URL 模板
    # NeoForge 1.21+ 的版本号格式为 {mc_version}-{loader_version}（如 1.21.1-21.1.228）
    # 但旧版格式为 {loader_version}（如 47.1.3）
    # BMCLAPI 镜像路径
    urls.append(
        f"{BMCLAPI.base_url}/maven/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}-installer.jar"
    )
    # 官方 maven
    urls.append(
        f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}-installer.jar"
    )
    return urls


def build_server_jar_urls(mc_version: str, loader_type: LoaderType, loader_version: str | None) -> list[str]:
    """构造服务端核心 .jar / installer 的候选下载 URL（同步版本）。

    优先使用 BMCLAPI（国内可用），然后回退到官方。

    注意：NeoForge 的 URL 需要动态获取，请使用 resolve_neoforge_installer_url()。

    Args:
        mc_version: 游戏版本（如 "1.20.1"）。
        loader_type: 加载器类型。
        loader_version: 加载器版本（如 "47.1.3"）。

    Returns:
        候选 URL 列表。
    """
    urls: list[str] = []

    if loader_type in (LoaderType.VANILLA, LoaderType.PAPER):
        # 原版服务端：BMCLAPI 版本清单 → Mojang 官方
        urls.append(f"{BMCLAPI.base_url}/version/{mc_version}/server")
        urls.append(f"{MOJANG_OFFICIAL.base_url}/mc/game/version_manifest_v2.json")

    elif loader_type == LoaderType.FORGE and loader_version:
        # Forge installer: BMCLAPI 镜像 → 官方 maven
        urls.append(
            f"{BMCLAPI.base_url}/mirrors/forge/download/{mc_version}/forge-{mc_version}-{loader_version}/installer.jar"
        )
        urls.append(
            f"https://maven.minecraftforge.net/net/minecraftforge/forge/{mc_version}-{loader_version}/forge-{mc_version}-{loader_version}-installer.jar"
        )

    elif loader_type == LoaderType.NEOFORGE and loader_version:
        # NeoForge: 使用静态降级 URL（推荐使用 resolve_neoforge_installer_url）
        urls.append(
            f"{BMCLAPI.base_url}/maven/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}-installer.jar"
        )
        urls.append(
            f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}-installer.jar"
        )

    elif loader_type == LoaderType.FABRIC and loader_version:
        # Fabric: BMCLAPI → 官方
        urls.append(f"{BMCLAPI.base_url}/mirrors/fabric-meta/{loader_version}")
        urls.append("https://meta.fabricmc.net/v2/versions/loader")

    elif loader_type == LoaderType.QUILT and loader_version:
        urls.append("https://maven.quiltmc.org/repository/release/org/quiltmc/quilt-loader")

    return urls
