"""builder.fetcher.downloader — 阶段三·httpx+asyncio 多源并发下载。

参考 PCL2 源竞争策略：同时向多个源发起请求，谁先返回数据就用谁，其余取消。
大文件（>20MB）自动使用 HTTP Range 分块并行下载，充分利用带宽。

核心优化（对标 PCL2 ModNet.vb）：
  - 无 HEAD 请求：直接 GET 流式读取响应头获取 content-length，省掉 509 次 RTT
  - 源竞争（racing）：多源同时请求，先响应者胜出，参考 PCL2 ModNet
  - 分块下载：大文件用 HTTP Range 分 N 块并行下载，参考 PCL2 分片下载
  - 慢速掐死：5s 内速度 <1KB/s 自动断开换源，参考 PCL2 Thread() line 1102
  - 断点续传：已存在的非空文件自动跳过
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import httpx

from core.contracts import DownloadReport, LoaderType, Manifest, MissingMod, ModEntry

from .missing_log import MissingModLogger
from .sources import build_mod_urls, build_server_jar_urls, resolve_neoforge_installer_url

logger = logging.getLogger(__name__)

# ──────────────────────────── 常量 ────────────────────────────

# 全局并发数（同时下载的 mod 数量）
_GLOBAL_CONCURRENCY = 32

# 大文件分块下载阈值（字节），超过此大小使用分块
# PCL2: <1MB 不分割；我们提高到 20MB，减少中等文件的分块开销
_CHUNKED_THRESHOLD = 20 * 1024 * 1024  # 20MB

# 分块大小（每块 16MB，允许 8 个块并行 = 128MB 同时在传）
# PCL2: FilePieceLimit=256KB 最小碎片，动态追加；我们用固定大块减少请求数
_CHUNK_SIZE = 16 * 1024 * 1024

# 最大分块数（避免对 CDN 请求过多 Range）
_MAX_CHUNKS = 8

# 小文件超时（秒）
_SMALL_TIMEOUT = 30.0

# 大文件单块超时（秒）
_CHUNK_TIMEOUT = 120.0

# 慢速掐死阈值：连续 N 秒平均速度低于此值则断开（参考 PCL2 line 1102-1104）
# PCL2 用 85% of recent average 作为速度地板，我们用固定阈值
# 注意：1KB/s 太激进，32 并发时带宽被挤占容易误杀；改为 512B/s + 10s 容忍
_SLOW_SPEED_BYTES = 512  # 512 B/s
_SLOW_TIMEOUT_SEC = 10.0  # 连续 10 秒低于阈值才断开

# UA 头
_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "*/*",
}

# 写入缓冲区
_WRITE_BUFFER = 65536


# ──────────────────────────── 源竞争下载 ────────────────────────────


async def _race_download(
    urls: list[str],
    dest: Path,
    client: httpx.AsyncClient,
    *,
    timeout: float = _SMALL_TIMEOUT,
) -> list[str]:
    """源竞争下载：同时向所有候选源发起请求，第一个成功返回数据的胜出。

    参考 PCL2 的源竞争策略：所有源同时请求，谁先返回 body 数据就用谁，
    其余请求立即取消。这比串行尝试快得多。

    优化：不再先 HEAD 再 GET，直接用 streaming GET 读取响应头中的
    content-length 和 accept-ranges，省掉一次完整 RTT。

    Returns:
        尝试过的 URL 列表（空列表 = 已存在/成功跳过）。
    """
    # 断点续传：已有非空文件则跳过
    if dest.is_file() and dest.stat().st_size > 0:
        return []

    if not urls:
        return []

    dest.parent.mkdir(parents=True, exist_ok=True)

    # ── 只有一个源时直接下载（跳过竞争开销） ──
    if len(urls) == 1:
        ok = await _stream_download(urls[0], dest, client, timeout=timeout)
        return [] if ok else urls

    # ── 多源竞争 ──
    winner_idx = await _race_connect(urls, client, timeout=min(timeout, 15.0))

    if winner_idx >= 0:
        # 竞争胜出的源，用更长的超时完整下载
        ok = await _stream_download(urls[winner_idx], dest, client, timeout=timeout * 3)
        if ok:
            return []  # 成功

    # 竞争全部失败，降级为串行尝试
    tried: list[str] = []
    for url in urls:
        tried.append(url)
        ok = await _stream_download(url, dest, client, timeout=timeout * 3)
        if ok:
            return tried
        # 清理
        if dest.exists():
            dest.unlink()

    return tried


async def _race_connect(
    urls: list[str],
    client: httpx.AsyncClient,
    *,
    timeout: float = 10.0,
) -> int:
    """源竞争：同时发起流式请求，第一个成功返回数据的源胜出。

    参考 PCL2 的源竞争策略：所有源同时请求，谁先返回数据就用谁。
    这里只连接到获得 200 响应头，不下载 body 数据。
    胜出的源后续用 _stream_download 完整下载。

    Returns:
        胜出源的索引，-1 表示全部失败。
    """
    winner = asyncio.Event()
    result_idx = -1
    errors: list[Exception | None] = [None] * len(urls)

    async def _try_connect(idx: int, url: str) -> None:
        nonlocal result_idx
        try:
            # 用 stream 方式只读响应头，不读 body
            async with client.stream("GET", url, timeout=timeout, follow_redirects=True) as resp:
                if resp.status_code == 200 and not winner.is_set():
                    result_idx = idx
                    winner.set()
                # stream 会在 async with 退出时自动关闭
        except Exception as exc:
            errors[idx] = exc

    tasks = [asyncio.create_task(_try_connect(i, url)) for i, url in enumerate(urls)]

    try:
        await asyncio.wait_for(winner.wait(), timeout=timeout + 2)
    except asyncio.TimeoutError:
        pass
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    if result_idx < 0:
        # 全部失败，记录原因
        for i, exc in enumerate(errors):
            if exc:
                logger.debug("源竞争失败 [%s]: %s", _short_url(urls[i]), exc)

    return result_idx


# ──────────────────────────── 流式下载（无 HEAD） ────────────────────────────


async def _stream_download(
    url: str,
    dest: Path,
    client: httpx.AsyncClient,
    *,
    timeout: float = 60.0,
) -> bool:
    """流式下载单个 URL 到文件。支持大文件分块并行。

    优化：不再先发 HEAD 请求，而是直接用 streaming GET 读取响应头中的
    content-length 和 accept-ranges，省掉一次完整 RTT（参考 PCL2 Thread()
    line 994-1049，PCL2 从不发 HEAD，首线程直接 GET 读 ContentLength）。

    自动检测文件大小：
    - 小文件（<20MB）：直接流式下载
    - 大文件（>=20MB）且支持 Range：分块并行下载
    - 大文件不支持 Range：退化为流式下载

    Returns:
        True 下载成功，False 失败。
    """
    try:
        # ── 直接 GET 流式读取，从响应头获取文件信息 ──
        async with client.stream("GET", url, timeout=timeout, follow_redirects=True) as resp:
            if resp.status_code != 200:
                # 非 200 直接报错
                await resp.aread()  # 消费 body 以释放连接
                raise httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}", request=resp.request, response=resp
                )

            total_size = int(resp.headers.get("content-length", 0))
            accepts_range = "bytes" in resp.headers.get("accept-ranges", "").lower()

            # 大文件 + 支持 Range → 关闭此流，改用分块下载
            if total_size >= _CHUNKED_THRESHOLD and accepts_range:
                # 需要先关闭当前 stream 再开分块下载
                await resp.aclose()
                return await _chunked_download(url, dest, client, total_size, timeout)

            # ── 小文件或不支持 Range → 直接流式写入 ──
            with open(dest, "wb") as f:
                last_data_time = time.monotonic()
                slow_since: float | None = None  # 开始连续慢速的时刻，None=未触发
                bytes_since_last = 0

                async for chunk in resp.aiter_bytes(_WRITE_BUFFER):
                    f.write(chunk)

                    # 慢速掐死检测（参考 PCL2 line 1102-1104）
                    bytes_since_last += len(chunk)
                    now = time.monotonic()
                    elapsed = now - last_data_time

                    if elapsed >= 1.0:  # 每秒检查一次
                        speed = bytes_since_last / elapsed
                        if speed < _SLOW_SPEED_BYTES:
                            # 速度低于阈值：记录开始时刻或持续计时
                            if slow_since is None:
                                slow_since = now
                            if now - slow_since >= _SLOW_TIMEOUT_SEC:
                                raise TimeoutError(
                                    f"速度过慢断开 ({speed:.0f} B/s，已持续 {now - slow_since:.1f}s)"
                                )
                        else:
                            # 速度恢复，重置计时
                            slow_since = None
                        bytes_since_last = 0
                        last_data_time = now

        logger.info("下载成功: %s → %s (%s)", _short_url(url), dest.name, _human_size(dest.stat().st_size))
        return True

    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.warning("下载失败 [%s]: %s — %s", _short_url(url), dest.name, exc)
        if dest.exists():
            dest.unlink()
        return False
    except TimeoutError as exc:
        logger.warning("下载超时(慢速) [%s]: %s — %s", _short_url(url), dest.name, exc)
        if dest.exists():
            dest.unlink()
        return False
    except Exception as exc:
        logger.warning("下载异常 [%s]: %s — %s", _short_url(url), dest.name, exc)
        if dest.exists():
            dest.unlink()
        return False


# ──────────────────────────── 分块并行下载 ────────────────────────────


async def _chunked_download(
    url: str,
    dest: Path,
    client: httpx.AsyncClient,
    total_size: int,
    timeout: float,
) -> bool:
    """大文件分块并行下载。

    将文件分成 N 块（每块 _CHUNK_SIZE），用 asyncio.gather 并行下载所有块，
    最后合并成完整文件。参考 PCL2 的分片下载模式。

    临时文件格式：{dest}.part0, {dest}.part1, ...
    """
    n_chunks = min((total_size + _CHUNK_SIZE - 1) // _CHUNK_SIZE, _MAX_CHUNKS)
    # 调整块大小使每块均匀
    chunk_size = (total_size + n_chunks - 1) // n_chunks

    logger.info(
        "分块下载: %s (%s, %d 块)",
        dest.name, _human_size(total_size), n_chunks,
    )

    # 生成各块的 Range
    ranges = []
    for i in range(n_chunks):
        start = i * chunk_size
        end = min(start + chunk_size - 1, total_size - 1)
        if start > total_size - 1:
            break
        ranges.append((i, start, end))

    # 并行下载各块（带重试）
    sem = asyncio.Semaphore(n_chunks)  # 限制最大并行块数
    _CHUNK_RETRIES = 3  # 每块最多重试次数
    _range_not_supported = False  # 如果服务器忽略 Range，标记后回退到普通下载

    async def _download_chunk(idx: int, start: int, end: int) -> bool:
        nonlocal _range_not_supported
        if _range_not_supported:
            return False  # 服务器不支持 Range，放弃分块
        part_path = dest.parent / f"{dest.name}.part{idx}"
        # 块已存在且大小正确 → 跳过（断点续传）
        if part_path.is_file():
            expected_size = end - start + 1
            if part_path.stat().st_size == expected_size:
                return True

        async with sem:
            for attempt in range(1, _CHUNK_RETRIES + 1):
                try:
                    headers = {**_DEFAULT_HEADERS, "Range": f"bytes={start}-{end}"}
                    async with client.stream(
                        "GET", url, headers=headers,
                        timeout=timeout, follow_redirects=True,
                    ) as resp:
                        if resp.status_code == 200:
                            # 服务器忽略了 Range，返回了整个文件
                            # 标记后回退到普通下载
                            _range_not_supported = True
                            await resp.aread()
                            raise httpx.HTTPStatusError(
                                "服务器不支持 Range (返回 200 而非 206)",
                                request=resp.request, response=resp,
                            )
                        if resp.status_code != 206:
                            await resp.aread()
                            raise httpx.HTTPStatusError(
                                f"HTTP {resp.status_code}", request=resp.request, response=resp
                            )
                        with open(part_path, "wb") as f:
                            async for chunk in resp.aiter_bytes(_WRITE_BUFFER):
                                f.write(chunk)
                    # 校验块大小（必须精确匹配预期大小）
                    actual_size = part_path.stat().st_size
                    expected_size = end - start + 1
                    if actual_size == expected_size:
                        return True
                    # 大小不匹配：可能是服务器忽略了 Range 返回了整个文件
                    logger.warning(
                        "分块 %d 大小不匹配: 期望 %d 字节, 实际 %d 字节",
                        idx, expected_size, actual_size,
                    )
                    part_path.unlink(missing_ok=True)
                except Exception as exc:
                    logger.warning("分块 %d 下载失败(尝试 %d/%d): %s", idx, attempt, _CHUNK_RETRIES, exc)
                    part_path.unlink(missing_ok=True)
                    if attempt < _CHUNK_RETRIES:
                        await asyncio.sleep(1.0 * attempt)  # 递增退避
            return False

    results = await asyncio.gather(*[
        _download_chunk(idx, start, end) for idx, start, end in ranges
    ])

    # 检查是否所有块都成功
    failed_chunks = [idx for idx, ok in enumerate(results) if not ok]
    if failed_chunks:
        # 只清理失败的块，保留成功的块供下次断点续传
        for idx in failed_chunks:
            part_path = dest.parent / f"{dest.name}.part{idx}"
            part_path.unlink(missing_ok=True)
        logger.warning("分块下载失败（%d/%d 块未完成）: %s", len(failed_chunks), n_chunks, dest.name)
        return False

    # 合并块
    try:
        with open(dest, "wb") as out:
            for idx, _, _ in ranges:
                part_path = dest.parent / f"{dest.name}.part{idx}"
                with open(part_path, "rb") as part:
                    out.write(part.read())
                part_path.unlink()  # 合并后删除临时块

        logger.info("分块下载完成: %s (%s, %d 块)", dest.name, _human_size(dest.stat().st_size), n_chunks)
        return True
    except Exception as exc:
        logger.error("合并分块失败: %s — %s", dest.name, exc)
        if dest.exists():
            dest.unlink()
        return False


# ──────────────────────────── 单 Mod 下载 ────────────────────────────


async def _download_mod(
    entry: ModEntry,
    manifest: Manifest,
    mods_dir: Path,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    *,
    timeout: float = _SMALL_TIMEOUT,
) -> tuple[ModEntry, bool, list[str], str]:
    """下载单个模组（受信号量限流）。"""
    urls = build_mod_urls(entry, manifest)
    if not urls:
        return entry, False, [], "无可用下载源"

    async with sem:
        tried = await _race_download(urls, mods_dir / entry.filename, client, timeout=timeout)

    # 空列表 = 已存在或成功
    if not tried:
        return entry, True, [], ""

    # 检查文件是否成功写入
    dest = mods_dir / entry.filename
    if dest.is_file() and dest.stat().st_size > 0:
        return entry, True, tried, ""

    return entry, False, tried, "所有源均下载失败"


# ──────────────────────────── 服务端核心下载 ────────────────────────────


async def _download_server_jar(
    manifest: Manifest,
    sandbox: Path,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
) -> tuple[list[Path], list[str]]:
    """下载服务端核心安装器/核心 jar。"""
    if manifest.loader_type == LoaderType.NEOFORGE and manifest.loader_version:
        urls = await resolve_neoforge_installer_url(
            manifest.mc_version, manifest.loader_version
        )
    else:
        urls = build_server_jar_urls(
            manifest.mc_version, manifest.loader_type, manifest.loader_version
        )

    if not urls:
        return [], []

    loader_ver = manifest.loader_version or "unknown"
    dest = sandbox / f"{manifest.loader_type.value}-{loader_ver}-installer.jar"
    async with sem:
        tried = await _race_download(urls, dest, client, timeout=120.0)

    if not tried:
        return [dest], []

    artifacts = [dest] if dest.exists() else []
    return artifacts, tried


# ──────────────────────────── 主入口 ────────────────────────────


async def fetch_all(
    manifest: Manifest,
    sandbox: Path,
    *,
    client: httpx.AsyncClient | None = None,
    concurrency: int | None = None,
    timeout: float = _SMALL_TIMEOUT,
) -> DownloadReport:
    """统一并发下载清单中所有模组与服务端核心。

    策略：
      - 全局 32 并发（不区分大小文件）
      - 多源竞争：同时向所有候选源发起请求，先响应者胜出
      - 大文件（>=20MB）自动分块并行下载（最多 8 块）
      - 无 HEAD 请求：直接 GET 流式读取，省掉一次 RTT
      - 慢速掐死：5s 内速度 <1KB/s 自动断开换源
      - 断点续传：已存在的非空文件自动跳过

    Args:
        manifest: 解析后的整合包元数据。
        sandbox: 当前构建沙箱目录。
        client: 外部注入的 httpx 客户端。为 None 时创建默认客户端。
        concurrency: 自定义并发数（覆盖默认值）。
        timeout: 单个 URL 超时（秒）。

    Returns:
        DownloadReport（含成功列表、缺失列表）。
    """
    conc = concurrency or _GLOBAL_CONCURRENCY
    close_on_exit = False

    if client is None:
        client = httpx.AsyncClient(
            headers=_DEFAULT_HEADERS,
            timeout=timeout,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=256,          # 高并发需要大连接池
                max_keepalive_connections=64,
            ),
        )
        close_on_exit = True

    try:
        mods_dir = sandbox / "mods"
        mods_dir.mkdir(parents=True, exist_ok=True)

        succeeded: list[ModEntry] = []
        missing: list[MissingMod] = []

        # ── 并发下载所有 mod ──
        logger.info("开始下载 %d 个模组（并发=%d，源竞争+分块，无HEAD）...", len(manifest.mods), conc)
        sem = asyncio.Semaphore(conc)
        coros = [
            _download_mod(entry, manifest, mods_dir, client, sem, timeout=timeout)
            for entry in manifest.mods
        ]
        results = await asyncio.gather(*coros)

        for entry, ok, tried, reason in results:
            if ok:
                succeeded.append(entry)
            else:
                missing.append(MissingMod(entry=entry, reason=reason, tried_sources=tried))

        # ── 下载服务端核心 ──
        sem_install = asyncio.Semaphore(1)
        server_artifacts, _ = await _download_server_jar(manifest, sandbox, client, sem_install)

        # ── 写入 missing_mods.log ──
        report = DownloadReport(
            succeeded=succeeded,
            missing=missing,
            server_artifacts=server_artifacts,
        )
        if missing:
            log_path = sandbox / "missing_mods.log"
            MissingModLogger(log_path).log(missing)
            logger.warning("共 %d 个模组下载失败，已记录到 %s", len(missing), log_path)

        logger.info("下载完成：成功 %d / 失败 %d / 核心产物 %d",
                     len(succeeded), len(missing), len(server_artifacts))
        return report

    finally:
        if close_on_exit:
            await client.aclose()


# ──────────────────────────── 工具函数 ────────────────────────────


def _short_url(url: str, max_len: int = 60) -> str:
    return url if len(url) <= max_len else url[:max_len - 3] + "..."


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"
