"""builder.unpack.safe_extract — 阶段一·安全解压，防御 Zip Slip 目录穿越漏洞。

将用户上传的 ZIP 解压至系统临时沙箱目录，禁止任何 entry 写出沙箱根之外。
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from ..errors import ZipSlipError


def _decode_name(raw: str) -> str:
    """修复 Windows 上 zipfile 默认 cp437 解码导致的中文乱码。

    zipfile 在未设置 UTF-8 flag 时按 cp437 解码文件名；中文环境需要回退尝试 gbk/utf-8。
    """
    try:
        # 反编码回字节再按 gbk 解码（国内整合包常见）
        return raw.encode("cp437").decode("gbk")
    except (UnicodeDecodeError, UnicodeEncodeError):
        try:
            return raw.encode("cp437").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            return raw


def extract_zip(zip_path: Path, dest: Path) -> Path:
    """将 ZIP 安全解压到 dest 目录。

    安全策略：
        对每个 entry，计算 (dest / name).resolve()，必须以 dest.resolve() 为前缀，
        否则判定为 Zip Slip 攻击并抛出 ZipSlipError，跳过整个解压。

    Returns:
        dest（解压目标目录的 resolved 绝对路径）。

    Raises:
        ZipSlipError: 检测到目录穿越。
        FileNotFoundError: zip_path 不存在。
    """
    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP not found: {zip_path}")

    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()

    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            # 还原中文文件名：仅当未声明 UTF-8 flag 时回退解码
            name = _decode_name(info.filename) if info.flag_bits & 0x800 == 0 else info.filename
            # 规范化目标路径
            target = (dest_resolved / name).resolve()
            # Zip Slip 核心防御：目标必须在沙箱根之内
            try:
                target.relative_to(dest_resolved)
            except ValueError:
                raise ZipSlipError(info.filename, str(dest_resolved)) from None

            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src, open(target, "wb") as out:
                    # 分块写出避免大文件占内存
                    while True:
                        chunk = src.read(65536)
                        if not chunk:
                            break
                        out.write(chunk)

    return dest_resolved
