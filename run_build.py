"""一键构建脚本 — 自动接受 EULA，从 ZIP 构建服务端工作目录。

支持续传：当 .sandbox/ 下已有未完成的构建目录时，自动检测并从断点继续。
使用 --fresh 参数强制从头开始（清理已有沙箱）。
"""
import asyncio
import logging
import shutil
import sys
from pathlib import Path

from builder import build_workspace
from builder.errors import BuildError, EulaRejectedError
from builder.merge.eula_gate import EulaGate
from core.contracts import EulaDecision
from core.paths import SANDBOX_ROOT, instance_path


class AutoAcceptEulaGate:
    """自动接受 EULA 的闸门（用于无人值守构建）。"""

    async def request(self, timeout: float = 300) -> EulaDecision:
        print("✅ 已自动接受 Minecraft EULA")
        return EulaDecision.ACCEPTED


def _find_existing_sandbox() -> Path | None:
    """在 .sandbox/ 下查找已有的构建沙箱（含 manifest.json 的目录）。

    优先返回 mods 数量最多的沙箱（最有价值的续传点）。
    """
    if not SANDBOX_ROOT.is_dir():
        return None

    candidates: list[tuple[int, Path]] = []
    for d in SANDBOX_ROOT.iterdir():
        if not d.is_dir():
            continue
        # 检查是否含有 manifest.json（解压后的 CF 整合包）
        if (d / "manifest.json").is_file():
            # 统计已下载的 mod 数量
            mods_dir = d / "mods"
            if mods_dir.is_dir():
                mod_count = sum(
                    1 for f in mods_dir.iterdir()
                    if f.is_file() and f.stat().st_size > 0
                )
            else:
                mod_count = 0
            candidates.append((mod_count, d))

    if not candidates:
        return None

    # 返回 mod 数量最多的
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 解析参数
    fresh_mode = "--fresh" in sys.argv

    zip_path = Path("All the Mods 10-7.0.zip").resolve()
    if not zip_path.is_file():
        print(f"❌ 文件不存在: {zip_path}", file=sys.stderr)
        sys.exit(1)

    instance_id = "atm10"

    # 查找已有沙箱
    resume_sandbox = None
    if not fresh_mode:
        existing = _find_existing_sandbox()
        if existing:
            mods_dir = existing / "mods"
            mod_count = sum(
                1 for f in mods_dir.iterdir()
                if f.is_file() and f.stat().st_size > 0
            ) if mods_dir.is_dir() else 0
            print(f"🔄 检测到已有沙箱: {existing.name}（已下载 {mod_count} 个 mod）")
            print(f"   将从断点继续下载...")
            resume_sandbox = existing
        else:
            print("📦 全新构建")
    else:
        # 清理所有已有沙箱
        if SANDBOX_ROOT.is_dir():
            for d in SANDBOX_ROOT.iterdir():
                if d.is_dir():
                    print(f"🗑️  清理沙箱: {d.name}")
                    shutil.rmtree(d, ignore_errors=True)
        # 清理旧的交付目录
        old_dest = instance_path(instance_id)
        if old_dest.exists():
            print(f"🗑️  清理旧实例: {old_dest}")
            shutil.rmtree(old_dest, ignore_errors=True)
        print("📦 全新构建（--fresh）")

    print(f"📦 构建目标: {zip_path.name} → instance_{instance_id}")
    print()

    try:
        result = await build_workspace(
            zip_path=zip_path,
            instance_id=instance_id,
            eula_gate=AutoAcceptEulaGate(),
            resume_sandbox=resume_sandbox,
        )
    except EulaRejectedError as exc:
        print(f"\n🚫 {exc}", file=sys.stderr)
        sys.exit(2)
    except BuildError as exc:
        print(f"\n❌ 构建失败: {exc}", file=sys.stderr)
        sys.exit(1)

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
        for m in result.missing[:10]:
            print(f"      - {m.entry.filename}: {m.reason}")
        if len(result.missing) > 10:
            print(f"      ... 还有 {len(result.missing) - 10} 个")
        print("  请手动补全上述模组。")
    if result.manifest:
        print(f"  MC版本: {result.manifest.mc_version}")
        print(f"  加载器: {result.manifest.loader_type.value}-{result.manifest.loader_version}")


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


if __name__ == "__main__":
    asyncio.run(main())
