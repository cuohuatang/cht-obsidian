"""② 自动总结模块（源自 agentmemory mem::compress 设计）。

v0 为启发式聚合：把指定日期范围的流水/教训合并成结构化经验笔记。
LLM 增强（宿主 Agent 回调或本地模型）留待迭代。
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from ..config import VAULT_DIRS
from ..storage import vault


def summarize(days: int = 1, output_dir: str = "04-经验总结") -> dict[str, Any]:
    """把最近 N 天流水整理为结构化经验，写入经验总结目录。"""
    since = (date.today() - timedelta(days=days)).isoformat()
    notes: list[str] = []
    for rel, _ in vault._walk_vault():  # noqa: SLF001 —— 骨架阶段直接复用
        if VAULT_DIRS["memory"] not in rel:
            continue
        try:
            note = vault.read_note(rel)
            if note["meta"].get("updated", "")[:10] >= since:
                notes.append(f"- {note['meta'].get('title','')}：{note['content'][:120]}")
        except Exception:  # noqa: BLE001
            continue
    body = f"# 经验总结（{since} 起）\n\n## 要点\n\n" + ("\n".join(notes) if notes else "（无新流水）")
    note_id = f"sum-{uuid.uuid4().hex[:12]}"
    rel = f"{output_dir}/{date.today().isoformat()}-{note_id}.md"
    meta = {"note_id": note_id, "title": f"经验总结 {date.today().isoformat()}", "type": "summary"}
    return vault.write_note(rel, body, meta)


def weekly(scope: str = "week") -> dict[str, Any]:
    """每周规则：流水 + 踩坑 + 纠错 → 方法论（v0 汇总，规则增强待迭代）。"""
    return summarize(days=7, output_dir=VAULT_DIRS["summaries"])
