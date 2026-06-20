"""builder.errors — 模块一·流水线异常类型。"""
from __future__ import annotations


class BuildError(Exception):
    """builder 模块所有异常的基类。"""


class ZipSlipError(BuildError):
    """检测到 Zip Slip（目录穿越）攻击，拒绝解压该 entry。"""

    def __init__(self, entry: str, dest: str) -> None:
        self.entry = entry
        self.dest = dest
        super().__init__(
            f"Zip Slip detected: entry {entry!r} would escape sandbox {dest!r}"
        )


class UnrecognizedPackError(BuildError):
    """无法判别输入模式：既非引导包也非完整客户端。"""


class EulaRejectedError(BuildError):
    """用户拒绝 EULA 或超时未确认，流水线熔断。

    message 区分拒绝与超时两种语义，便于上层给出对应文案。
    """

    def __init__(self, decision: str) -> None:
        self.decision = decision
        if decision == "timeout":
            msg = "由于您未在规定时间内确认 Mojang EULA 协议，服务端目录构建已终止。"
        else:
            msg = "由于您拒绝了 Mojang EULA 协议，服务端目录构建已终止。"
        super().__init__(msg)


class IntegrityError(BuildError):
    """资产封账失败：缺少核心 / EULA 未签 / 文件损坏等。"""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("完整性校验未通过：" + "; ".join(issues))
