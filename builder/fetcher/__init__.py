"""builder.fetcher — 阶段三·云端多源依赖解析与下载。"""
from .downloader import fetch_all
from .missing_log import MissingModLogger
from .sources import DownloadSource, BMCLAPI, MCIMIRROR, CURSEFORGE_EDGE, CURSEFORGE_MEDIA, MODRINTH_CDN, MOJANG_OFFICIAL

__all__ = [
    "fetch_all",
    "MissingModLogger",
    "DownloadSource",
    "BMCLAPI",
    "MCIMIRROR",
    "CURSEFORGE_EDGE",
    "CURSEFORGE_MEDIA",
    "MODRINTH_CDN",
    "MOJANG_OFFICIAL",
]
