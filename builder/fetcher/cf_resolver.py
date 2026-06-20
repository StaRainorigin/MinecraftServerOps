"""builder.fetcher.cf_resolver — CurseForge 文件名解析器。

CurseForge 的 manifest.json 只提供 (projectID, fileID)，不含真实文件名和下载 URL。
本模块通过 CF 下载重定向接口批量解析出每个模组的真实文件名和 CDN 下载地址。

两种策略（自动选择）：
    A. 有 CF_API_KEY 时：调用官方 Core API 获取 downloadUrl，速度快、无限制
    B. 无 API Key 时：用 cloudscraper 绕过 Cloudflare 访问 307 重定向接口

结果缓存到本地 JSON，断点续传时跳过已解析条目。
解析失败的条目降级为 {pid}-{fid}.jar 占位文件名。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import NamedTuple

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

# CF 下载重定向端点（cloudscraper 方式）
_CF_DOWNLOAD_URL = "https://www.curseforge.com/api/v1/mods/{pid}/files/{fid}/download"

# CF Core API 端点（API Key 方式）
_CF_API_BASE = "https://api.curseforge.com"

# 缓存文件名
_CACHE_FILENAME = "cf_resolve_cache.json"


class ResolvedFile(NamedTuple):
    """解析结果：真实文件名 + CDN 下载 URL。"""

    filename: str
    download_url: str


def _cache_path() -> Path:
    """返回缓存文件路径。"""
    from core.paths import DOWNLOAD_CACHE
    return DOWNLOAD_CACHE / _CACHE_FILENAME


def _load_cache() -> dict[str, dict[str, str]]:
    """加载已有缓存。key = "{pid}:{fid}", value = {"filename": ..., "download_url": ...}。"""
    path = _cache_path()
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("缓存文件损坏，将重建: %s (%s)", path, exc)
    return {}


def _save_cache(cache: dict[str, dict[str, str]]) -> None:
    """持久化缓存到磁盘。"""
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


# ──────────────────────────── 策略 A：CF Core API ────────────────────────────


def _resolve_one_api(pid: str, fid: str, api_key: str) -> ResolvedFile | None:
    """通过 CF Core API 获取文件下载链接。

    API 文档：https://docs.curseforge.com/rest-api/
    端点：GET /v1/mods/{pid}/files/{fid}
    Header：x-api-key: {api_key}

    返回的 JSON 中 file.downloadUrl 即为 CDN 直链（含真实文件名）。
    """
    url = f"{_CF_API_BASE}/v1/mods/{pid}/files/{fid}"
    headers = {
        "x-api-key": api_key,
        "Accept": "application/json",
    }
    try:
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        if resp.status_code != 200:
            logger.warning(
                "CF API 返回非 200: pid=%s fid=%s status=%d",
                pid, fid, resp.status_code,
            )
            return None

        data = resp.json()
        file_data = data.get("data")
        if not file_data:
            logger.warning("CF API 返回空 data: pid=%s fid=%s", pid, fid)
            return None

        download_url = file_data.get("downloadUrl", "")
        filename = file_data.get("fileName", "")

        # 有些文件 downloadUrl 可能为空（被作者撤回等）
        if not download_url:
            # 尝试从 isAvailable 判断
            if not file_data.get("isAvailable", True):
                logger.warning("CF 文件不可用: pid=%s fid=%s", pid, fid)
                return None
            # 尝试手动构建 CDN URL
            if filename:
                download_url = _build_cdn_url(fid, filename)

        if not filename and download_url:
            # 从 URL 提取文件名
            filename = download_url.split("/")[-1].split("?")[0]

        if not filename:
            logger.warning("CF API 无法获取文件名: pid=%s fid=%s", pid, fid)
            return None

        # 将 edge URL 转换为 mediafilez 直连
        direct_url = download_url.replace("edge.forgecdn.net", "mediafilez.forgecdn.net")

        return ResolvedFile(filename=filename, download_url=direct_url)

    except Exception as exc:
        logger.warning("CF API 解析异常: pid=%s fid=%s -> %s", pid, fid, exc)
        return None


def _resolve_batch_api(
    entries: list[tuple[str, str]],
    api_key: str,
) -> dict[str, ResolvedFile]:
    """通过 CF Core API 批量解析。

    使用 /v1/mods/files 端点批量查询，减少请求次数。
    """
    results: dict[str, ResolvedFile] = {}

    # CF API 的批量端点：POST /v1/mods/files
    # body: {"fileIds": [1234, 5678, ...]}
    # 但这个端点有上限（最多 1000 个），481 个 mod 可以一次搞定
    file_ids = [int(fid) for _, fid in entries]
    pid_map = {fid: pid for pid, fid in entries}  # fid → pid 映射

    url = f"{_CF_API_BASE}/v1/mods/files"
    headers = {
        "x-api-key": api_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    # 分批请求（每批 500，避免超限）
    batch_size = 500
    for start in range(0, len(file_ids), batch_size):
        batch = file_ids[start:start + batch_size]
        body = {"fileIds": batch}

        try:
            resp = httpx.post(url, headers=headers, json=body, timeout=30, follow_redirects=True)
            if resp.status_code != 200:
                logger.warning("CF API 批量查询失败: status=%d", resp.status_code)
                # 降级为逐个查询
                for pid, fid in entries[start:start + batch_size]:
                    resolved = _resolve_one_api(pid, fid, api_key)
                    if resolved:
                        key = f"{pid}:{fid}"
                        results[key] = resolved
                continue

            data = resp.json()
            files = data.get("data", [])
            for f in files:
                fid = str(f.get("id", ""))
                pid = pid_map.get(fid, str(f.get("modId", "")))
                filename = f.get("fileName", "")
                download_url = f.get("downloadUrl", "")

                if not download_url and filename:
                    download_url = _build_cdn_url(fid, filename)

                if not filename and download_url:
                    filename = download_url.split("/")[-1].split("?")[0]

                if filename:
                    direct_url = download_url.replace("edge.forgecdn.net", "mediafilez.forgecdn.net")
                    key = f"{pid}:{fid}"
                    results[key] = ResolvedFile(filename=filename, download_url=direct_url)

            logger.info("CF API 批量解析：%d/%d 成功", len(results), len(entries))

        except Exception as exc:
            logger.warning("CF API 批量查询异常: %s", exc)
            continue

    return results


def _build_cdn_url(fid: str, filename: str) -> str:
    """从 fileID 和 filename 构建 CDN URL。"""
    fid_int = int(fid)
    return f"https://mediafilez.forgecdn.net/files/{fid_int // 1000}/{fid_int % 1000}/{filename}"


# ──────────────────────────── 策略 B：cloudscraper ────────────────────────────


def _resolve_one_scraper(pid: str, fid: str) -> ResolvedFile | None:
    """通过 cloudscraper 绕过 Cloudflare 获取 307 重定向。"""
    import cloudscraper

    url = _CF_DOWNLOAD_URL.format(pid=pid, fid=fid)
    try:
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "desktop": True}
        )
        r = scraper.get(url, allow_redirects=False, timeout=30)

        if r.status_code not in (301, 302, 307, 308):
            logger.warning(
                "CF 解析未获得重定向: pid=%s fid=%s status=%d",
                pid, fid, r.status_code,
            )
            return None

        location = r.headers.get("location", "")
        if not location:
            logger.warning("CF 重定向缺少 Location 头: pid=%s fid=%s", pid, fid)
            return None

        # 从 URL 中提取文件名
        raw_name = location.split("/")[-1].split("?")[0]
        if not raw_name or "." not in raw_name:
            logger.warning(
                "CF 解析得到异常文件名: pid=%s fid=%s raw=%s",
                pid, fid, raw_name,
            )
            return None

        # edge → mediafilez 直连
        direct_url = location.replace("edge.forgecdn.net", "mediafilez.forgecdn.net")

        return ResolvedFile(filename=raw_name, download_url=direct_url)

    except Exception as exc:
        logger.warning("CF 解析异常: pid=%s fid=%s -> %s", pid, fid, exc)
        return None


# ──────────────────────────── 主入口 ────────────────────────────


def resolve_batch(
    entries: list[tuple[str, str]],
    *,
    progress_callback: object = None,
) -> dict[str, ResolvedFile]:
    """批量解析 CF 模组文件名。

    有 CF_API_KEY 时使用官方 API（快速、无限制），
    否则使用 cloudscraper 绕过 Cloudflare（慢、可能被限流）。

    Args:
        entries: [(project_id, file_id), ...] 列表。
        progress_callback: 可选进度回调（暂未实现）。

    Returns:
        字典 {"pid:fid": ResolvedFile, ...}，解析失败的条目不在结果中。
    """
    cache = _load_cache()
    results: dict[str, ResolvedFile] = {}
    new_entries: list[tuple[str, str]] = []

    # 第一遍：从缓存中命中
    for pid, fid in entries:
        key = f"{pid}:{fid}"
        if key in cache:
            cached = cache[key]
            results[key] = ResolvedFile(
                filename=cached["filename"],
                download_url=cached["download_url"],
            )
        else:
            new_entries.append((pid, fid))

    if not new_entries:
        logger.info("CF 解析：全部 %d 条缓存命中", len(entries))
        return results

    logger.info(
        "CF 解析：缓存命中 %d/%d，需解析 %d 个",
        len(results), len(entries), len(new_entries),
    )

    # 第二遍：解析新条目
    api_key = settings.cf_api_key
    if api_key:
        # ── 策略 A：CF Core API ──
        logger.info("使用 CF Core API 解析（API Key 已配置）")
        api_results = _resolve_batch_api(new_entries, api_key)
        results.update(api_results)

        # 更新缓存
        for key, resolved in api_results.items():
            cache[key] = {
                "filename": resolved.filename,
                "download_url": resolved.download_url,
            }
        _save_cache(cache)

        # 处理 API 也未能解析的条目
        failed = [(pid, fid) for pid, fid in new_entries
                  if f"{pid}:{fid}" not in results]
        if failed:
            logger.info("CF API 未解析 %d 条，尝试 cloudscraper 兜底...", len(failed))
            _resolve_remaining_scraper(failed, results, cache)
    else:
        # ── 策略 B：cloudscraper ──
        logger.info("使用 cloudscraper 解析（无 API Key，速度较慢）")
        _resolve_remaining_scraper(new_entries, results, cache)

    return results


def _resolve_remaining_scraper(
    entries: list[tuple[str, str]],
    results: dict[str, ResolvedFile],
    cache: dict[str, dict[str, str]],
) -> None:
    """用 cloudscraper 逐个解析剩余条目。"""
    resolved_count = 0
    failed_count = 0

    for i, (pid, fid) in enumerate(entries, 1):
        key = f"{pid}:{fid}"
        resolved = _resolve_one_scraper(pid, fid)
        if resolved is not None:
            results[key] = resolved
            cache[key] = {
                "filename": resolved.filename,
                "download_url": resolved.download_url,
            }
            resolved_count += 1
        else:
            failed_count += 1

        # 每 50 条或最后一条时保存缓存
        if i % 50 == 0 or i == len(entries):
            _save_cache(cache)
            logger.info(
                "CF 解析进度：%d/%d（成功=%d 失败=%d）",
                i, len(entries), resolved_count, failed_count,
            )

    logger.info(
        "CF cloudscraper 解析完成：共 %d 条，成功=%d 失败=%d",
        len(entries), resolved_count, failed_count,
    )
