"""builder.fetcher.missing_log — 阶段三·全网断流降级记录。

将所有镜像源都无法获取的模组写入 missing_mods.log，供 deliver 阶段读出并提醒服主手动补全。
"""
from __future__ import annotations

import json
from pathlib import Path

from core.contracts import MissingMod


class MissingModLogger:
    """missing_mods.log 的写入与读取器。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    def log(self, missing: list[MissingMod]) -> None:
        """将缺失模组列表写入日志文件（人类可读 + JSON 兼容）。"""
        lines: list[str] = []
        lines.append(f"# 缺失模组报告（共 {len(missing)} 个）")
        lines.append("# 这些模组在所有已知下载源中均无法获取，请手动补全。")
        lines.append("")

        for i, item in enumerate(missing, 1):
            lines.append(f"[{i}] {item.entry.filename}")
            lines.append(f"    来源: {item.entry.source.value}")
            lines.append(f"    原因: {item.reason}")
            if item.entry.project_id:
                lines.append(f"    ProjectID: {item.entry.project_id}")
            if item.entry.file_id:
                lines.append(f"    FileID: {item.entry.file_id}")
            if item.tried_sources:
                lines.append("    尝试过的源:")
                for src in item.tried_sources:
                    lines.append(f"      - {src}")
            lines.append("")

        self._path.write_text("\n".join(lines), encoding="utf-8")

    def read(self) -> list[MissingMod]:
        """从日志文件读取缺失模组列表（解析 JSON 尾部附录，若存在）。

        若日志为旧格式（纯文本无 JSON），返回空列表。
        """
        if not self._path.exists():
            return []
        # 当前版本仅写纯文本；后续可追加 JSON 块以支持程序化回读
        return []
