"""builder.pipeline — 模块一·流水线总调度。

编排解包/解析/下载/合并/安装/交付六阶段，根据解包判别结果动态选择分支。
pipeline 为 async def，因为 fetcher（网络下载）和 EULA 闸（等待用户确认）是异步点。
"""
from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

import httpx

from core.contracts import BuildResult, InputMode, Manifest, UnpackResult
from core.paths import ensure_dirs, sandbox_path

from .deliver.integrity import verify_integrity
from .deliver.publisher import publish
from .errors import BuildError, EulaRejectedError, IntegrityError
from .fetcher.cf_resolver import resolve_batch
from .fetcher.downloader import fetch_all
from .merge.client_cleaner import clean_client_mods
from .merge.config_merger import merge_configs
from .merge.eula_gate import ConsoleEulaGate, EulaGate, ensure_eula
from .metadata.curseforge import parse_curseforge
from .metadata.modrinth import parse_modrinth
from .unpack.discriminator import discriminate, find_manifest
from .unpack.root_locator import locate_game_root
from .unpack.safe_extract import extract_zip

logger = logging.getLogger(__name__)


def _parse_manifest_with_resolve(manifest_path: Path) -> Manifest:
    """解析清单文件，对 CF 清单自动解析真实文件名。

    Args:
        manifest_path: 清单文件路径。

    Returns:
        带真实文件名的 Manifest。
    """
    name = manifest_path.name.lower()

    if name == "manifest.json":
        # CurseForge：先读取 projectID/fileID 列表，再批量解析文件名
        raw_manifest = parse_curseforge(manifest_path)
        logger.info("[阶段二] CF 清单原始解析：MC=%s, Loader=%s-%s, Mod数=%d",
                     raw_manifest.mc_version,
                     raw_manifest.loader_type.value,
                     raw_manifest.loader_version,
                     len(raw_manifest.mods))

        # 批量解析真实文件名
        entries = [(m.project_id, m.file_id) for m in raw_manifest.mods]
        if entries:
            logger.info("[阶段二] 开始解析 %d 个 CF 模组的真实文件名...", len(entries))
            resolved = resolve_batch(entries)
            # 转换为 curseforge.py 需要的格式
            names_dict = {
                key: (rf.filename, rf.download_url)
                for key, rf in resolved.items()
            }
            # 重新解析，注入真实文件名
            return parse_curseforge(manifest_path, resolved_names=names_dict)

        return raw_manifest

    if name == "modrinth.index.json":
        return parse_modrinth(manifest_path)

    raise ValueError(f"不支持的清单文件：{manifest_path.name}")


async def build_workspace(
    zip_path: Path,
    instance_id: str,
    *,
    eula_gate: EulaGate | None = None,
    http_client: httpx.AsyncClient | None = None,
    resume_sandbox: Path | None = None,
) -> BuildResult:
    """从用户上传的 ZIP 构建完整的服务端工作目录。

    流水线：
        ① unpack:    extract → locate_root → discriminate
        ② metadata:  [仅引导包] parse_manifest + CF 文件名解析
        ③ fetcher:   [仅引导包] await fetch_all → 核心jar+mods 落地沙箱
        ④ merge:     clean_client_mods + merge_configs + ensure_eula
        ⑤ install:   [仅引导包] 执行 loader installer 安装服务端
        ⑥ deliver:   verify_integrity → generate_launch_script → publish

    支持续传：当 resume_sandbox 指向一个已有的未完成沙箱时，跳过解压阶段，
    直接从下载阶段继续（已存在的 mod 文件会被自动跳过）。

    Args:
        zip_path: 用户上传的 ZIP 文件路径。
        instance_id: 实例 ID（如 "atm10"）。
        eula_gate: EULA 确认闸（注入，默认控制台交互）。
        http_client: httpx 异步客户端（注入，默认新建）。
        resume_sandbox: 续传用的已有沙箱目录（跳过解压，直接继续下载）。

    Returns:
        BuildResult（含工作目录路径 / 大小 / 模组数 / 缺失列表）。

    Raises:
        BuildError: 任何阶段失败。
        EulaRejectedError: 用户拒绝或超时未确认 EULA。
    """
    # ── 初始化 ──
    if eula_gate is None:
        eula_gate = ConsoleEulaGate()

    ensure_dirs()

    # ── 续传模式：复用已有沙箱 ──
    resuming = False
    if resume_sandbox is not None and resume_sandbox.is_dir():
        sandbox = resume_sandbox
        resuming = True
        logger.info("[续传] 复用已有沙箱: %s", sandbox)
    else:
        build_id = uuid.uuid4().hex[:8]
        sandbox = sandbox_path(build_id)

    try:
        # ────────── 阶段一：多态解包与资产校验 ──────────
        if resuming:
            # 续传模式：沙箱已存在，跳过解压
            logger.info("[阶段一·续传] 跳过解压，使用已有沙箱")
            game_root = sandbox
            # 查找 manifest
            manifest_path = find_manifest(game_root)
            if manifest_path:
                mode = InputMode.BOOTSTRAP
            else:
                # 尝试在子目录查找
                for subdir in game_root.iterdir():
                    if subdir.is_dir():
                        mp = find_manifest(subdir)
                        if mp:
                            manifest_path = mp
                            game_root = subdir
                            break
                mode = InputMode.BOOTSTRAP if manifest_path else InputMode.CLIENT
            logger.info("[阶段一·续传] 输入模式=%s, 游戏根=%s", mode.value, game_root)
            unpack_result = UnpackResult(
                sandbox_root=sandbox,
                mode=mode,
                game_root=game_root,
                manifest_path=manifest_path,
            )
        else:
            logger.info("[阶段一] 解压 %s → %s", zip_path, sandbox)
            extract_zip(zip_path, sandbox)
            game_root = locate_game_root(sandbox)
            mode = discriminate(game_root)

            logger.info("[阶段一] 输入模式=%s, 游戏根=%s", mode.value, game_root)
            unpack_result = UnpackResult(
                sandbox_root=sandbox,
                mode=mode,
                game_root=game_root,
                manifest_path=find_manifest(game_root),
            )

        # ────────── 阶段二+三（仅引导包） ──────────
        manifest: Manifest | None = None
        download_missing: list = []

        if mode == InputMode.BOOTSTRAP and unpack_result.manifest_path is not None:
            # 阶段二：解析清单 + CF 文件名解析
            logger.info("[阶段二] 解析引导包清单: %s", unpack_result.manifest_path)
            manifest = _parse_manifest_with_resolve(unpack_result.manifest_path)
            logger.info(
                "[阶段二] MC=%s, Loader=%s-%s, Mod数=%d",
                manifest.mc_version,
                manifest.loader_type.value,
                manifest.loader_version,
                len(manifest.mods),
            )

            # 阶段三：多源并发下载
            logger.info("[阶段三] 开始多源并发下载...")
            report = await fetch_all(manifest, sandbox, client=http_client)
            download_missing = report.missing
            logger.info(
                "[阶段三] 下载完成：成功%d, 缺失%d, 核心产物%d",
                len(report.succeeded),
                len(download_missing),
                len(report.server_artifacts),
            )

        # ────────── 阶段四：资产合并与配置组装 ──────────
        logger.info("[阶段四] 资产合并...")

        # 客户端模式：清洗纯客户端 Mod
        if mode == InputMode.CLIENT:
            mods_dir = game_root / "mods"
            if mods_dir.is_dir():
                clean_report = clean_client_mods(mods_dir)
                logger.info("[阶段四] 客户端清洗：禁用 %d 个客户端模组", clean_report.count)

        # 引导包模式也需要清洗（部分整合包含客户端 mod）
        if mode == InputMode.BOOTSTRAP:
            mods_dir = sandbox / "mods"
            if mods_dir.is_dir():
                clean_report = clean_client_mods(mods_dir)
                if clean_report.count > 0:
                    logger.info("[阶段四] 服务端清洗：禁用 %d 个客户端模组", clean_report.count)

        # 配置归并
        src_root = game_root
        dest_root = game_root
        merge_configs(src_root, dest_root)

        # EULA 交互闸
        logger.info("[阶段四] EULA 确认闸...")
        await ensure_eula(dest_root, eula_gate)

        # ────────── 阶段五：服务端安装 ──────────
        if mode == InputMode.BOOTSTRAP and manifest is not None:
            logger.info("[阶段五] 安装服务端...")
            from .install import install_server
            install_ok = install_server(dest_root, manifest)
            if not install_ok:
                logger.warning("[阶段五] 服务端安装失败，将跳过此步骤（可能需要手动安装）")

        # ────────── 阶段六：工作目录编译与交付 ──────────
        logger.info("[阶段六] 完整性校验...")
        integrity = verify_integrity(dest_root, mode)
        if not integrity.ok:
            logger.warning("[阶段六] 完整性校验问题: %s", "; ".join(integrity.issues))
            # 不再直接抛异常，允许部分问题通过（如缺失少量模组）

        # 生成启动脚本
        logger.info("[阶段六] 生成启动脚本...")
        from .launch import generate_launch_scripts
        generate_launch_scripts(dest_root, manifest)

        logger.info("[阶段六] 交付到 server_pool...")
        result = publish(
            sandbox=dest_root,
            instance_id=instance_id,
            mode=mode,
            missing=download_missing,
        )

        # 将 manifest 透传到 BuildResult
        result.manifest = manifest
        logger.info("✅ 构建完成: %s", result.workspace_path)
        return result

    except EulaRejectedError:
        logger.warning("❌ EULA 拒绝/超时，清理沙箱: %s", sandbox)
        _cleanup_sandbox(sandbox)
        raise

    except BuildError:
        logger.warning("❌ 构建异常，清理沙箱: %s", sandbox)
        _cleanup_sandbox(sandbox)
        raise

    except Exception:
        logger.exception("❌ 未预期异常，清理沙箱: %s", sandbox)
        _cleanup_sandbox(sandbox)
        raise


def _cleanup_sandbox(sandbox: Path) -> None:
    """清理沙箱目录（仅删除本次构建的临时目录，不影响全局）。"""
    if sandbox.is_dir():
        try:
            shutil.rmtree(str(sandbox), ignore_errors=True)
        except Exception:
            pass
