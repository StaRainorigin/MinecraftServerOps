"""builder.merge.eula_gate — 阶段四·Human-in-the-loop EULA 交互闸。

系统严禁静默生成已同意的 eula.txt。
本模块定义 EulaGate 协议，pipeline 通过依赖注入使用，支持控制台交互 / API 回调 / Mock 测试。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from core.contracts import EulaDecision

from ..errors import EulaRejectedError

logger = logging.getLogger(__name__)

# Mojang EULA 标准文本
EULA_TEXT = """Minecraft EULA (https://aka.ms/MinecraftEULA)

BY USING THE MINECRAFT SOFTWARE AND SERVICES (THE "SOFTWARE"), YOU ACCEPT THE
FOLLOWING TERMS AND CONDITIONS. IF YOU DO NOT AGREE TO THESE TERMS AND CONDITIONS,
YOU MUST NOT USE THE SOFTWARE.

(完整文本请访问 https://aka.ms/MinecraftEULA)
"""

# 默认等待超时（秒）
_DEFAULT_TIMEOUT = 300  # 5 分钟


# ──────────────── 协议定义 ────────────────


class EulaGate(Protocol):
    """EULA 确认闸的协议（接口）。

    实现方可接入 CLI 控制台、Web 前端、Bot 机器人等任意交互通道。
    """

    async def request(self, timeout: float = _DEFAULT_TIMEOUT) -> EulaDecision:
        """向用户展示 EULA 文本并等待确认。

        Args:
            timeout: 超时秒数。

        Returns:
            ACCEPTED / REJECTED / TIMEOUT。
        """
        ...


# ──────────────── 默认实现（控制台交互）────────────────


class ConsoleEulaGate:
    """控制台 EULA 确认闸。适用于 CLI / 本地命令行运行场景。"""

    async def request(self, timeout: float = _DEFAULT_TIMEOUT) -> EulaDecision:
        """在控制台打印 EULA 并等待用户输入。"""
        print("\n" + "=" * 60)
        print("请阅读以下 Minecraft EULA 协议：")
        print("=" * 60)
        print(EULA_TEXT)
        print("=" * 60)
        print()
        print("请输入您的决定：")
        print("  [Y] 我同意上述协议（同意后系统将写入 eula=true）")
        print("  [N] 我拒绝上述协议（流水线将终止）")
        print(f"  （{int(timeout)} 秒内未输入将自动拒绝）")
        print()

        try:
            answer = await asyncio.wait_for(
                asyncio.to_thread(input, "您的选择 (Y/N): "),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return EulaDecision.TIMEOUT

        stripped = answer.strip().lower()
        if stripped in ("y", "yes", "是", "同意"):
            return EulaDecision.ACCEPTED
        return EulaDecision.REJECTED


# ──────────────── 工具函数 ────────────────


def write_eula(workspace: Path) -> None:
    """向工作目录写入 eula.txt（eula=true）。

    ⚠️ 仅在 EulaGate 返回 ACCEPTED 后方可调用。
    """
    eula_file = workspace / "eula.txt"
    eula_file.write_text(
        "# By changing the setting below to TRUE you are indicating your agreement to our EULA.\n"
        "# (https://aka.ms/MinecraftEULA)\n"
        "eula=true\n",
        encoding="utf-8",
    )
    logger.info("已写入 eula=true: %s", eula_file)


async def ensure_eula(
    workspace: Path,
    gate: EulaGate,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
) -> None:
    """执行 EULA 确认流程：展示 → 等待 → 判定 → 写入。

    本函数为 async，供 async pipeline 直接 await 调用。

    Args:
        workspace: 当前工作目录。
        gate: EULA 确认闸实例。
        timeout: 等待超时秒数。

    Raises:
        EulaRejectedError: 用户拒绝或超时，流水线应立即熔断。
    """
    # 如果 eula.txt 已存在且已同意，跳过（幂等）
    existing = workspace / "eula.txt"
    if existing.is_file() and "eula=true" in existing.read_text(encoding="utf-8"):
        logger.info("eula.txt 已存在且已同意，跳过确认")
        return

    decision = await gate.request(timeout=timeout)

    if decision != EulaDecision.ACCEPTED:
        raise EulaRejectedError(decision.value)

    write_eula(workspace)
