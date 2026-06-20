"""MC-SRE Builder CLI — 从命令行启动服务端工作目录构建。

用法:
    python -m builder <zip_path> <instance_id>

示例:
    python -m builder my_modpack.zip 001
    python -m builder D:\\packs\\client.zip my_server
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from . import build_workspace
from .errors import BuildError, EulaRejectedError


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="builder",
        description="MC-SRE 服务端工作目录构建器",
    )
    parser.add_argument(
        "zip_path",
        type=Path,
        help="用户上传的 ZIP 文件路径（引导包 / 完整客户端）",
    )
    parser.add_argument(
        "instance_id",
        type=str,
        help="实例 ID（如 001，对应 server_pool/instance_001/）",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="显示详细日志",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # 日志配置
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    zip_path = args.zip_path.resolve()
    if not zip_path.is_file():
        print(f"❌ 文件不存在: {zip_path}", file=sys.stderr)
        sys.exit(1)

    print(f"📦 开始构建: {zip_path.name} → instance_{args.instance_id}")
    print()

    try:
        result = asyncio.run(build_workspace(
            zip_path=zip_path,
            instance_id=args.instance_id,
        ))
    except EulaRejectedError as exc:
        print(f"\n🚫 {exc}", file=sys.stderr)
        sys.exit(2)
    except BuildError as exc:
        print(f"\n❌ 构建失败: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n⏹ 用户中断", file=sys.stderr)
        sys.exit(130)

    # 输出结果
    print()
    print("=" * 50)
    print("✅ 服务端工作目录构建完成！")
    print("=" * 50)
    print(f"  工作目录: {result.workspace_path}")
    print(f"  输入模式: {result.mode.value}")
    print(f"  模组总数: {result.mod_count}")
    print(f"  目录大小: {_human_size(result.total_size_bytes)}")
    if result.missing:
        print(f"  ⚠️  缺失模组: {len(result.missing)} 个")
        for m in result.missing:
            print(f"      - {m.entry.filename}: {m.reason}")
        print("  请手动补全上述模组。")
    print()


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"


if __name__ == "__main__":
    main()
