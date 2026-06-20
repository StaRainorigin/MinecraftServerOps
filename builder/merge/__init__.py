"""builder.merge — 阶段四·资产合并与配置组装。"""
from .blacklist import is_client_mod
from .client_cleaner import clean_client_mods, CleanReport
from .config_merger import merge_configs
from .eula_gate import ConsoleEulaGate, EulaGate, ensure_eula, write_eula

__all__ = [
    "is_client_mod",
    "clean_client_mods",
    "CleanReport",
    "merge_configs",
    "ConsoleEulaGate",
    "EulaGate",
    "ensure_eula",
    "write_eula",
]
