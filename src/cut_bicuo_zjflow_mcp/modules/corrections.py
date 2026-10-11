"""④ 纠错台账模块（AgentRecall 式）：结构化纠正 + 生效验证 + 开工检查。"""

from __future__ import annotations

import uuid
from typing import Any

from ..config import VAULT_DIRS
from ..storage import vault

_KIND = "correction"


def log(
    correction: str,
    evidence: str | None = None,
    severity: str = "medium",
    model: str | None = None,
    links: list[str] | None = None,
) -> dict[str, Any]:
    """每次用户纠正即结构化记录（严重度/证据）。

    links：Obsidian 双链回源列表（双链约定，见 DESIGN.md）。
    """
    note_id = f"cor-{uuid.uuid4().hex[:12]}"
    title = correction.strip().splitlines()[0][:40]
    rel = f"{VAULT_DIRS['corrections']}/{vault.slugify(title)}-{note_id[-6:]}.md"
    meta = {
        "note_id": note_id,
        "title": title,
        "type": _KIND,
        "severity": severity,
        "evidence": evidence or "",
        "model": model or "any",
        "status": "active",  # active → verified / superseded
        "links": links or [],
    }
    body = f"## 纠正\n{correction}\n\n## 证据/触发场景\n{evidence or '（待补充）'}\n\n## 是否生效\n待验证"
    if links:
        body += "\n\n## 相关笔记\n" + "\n".join(f"- [[{l}]]" for l in links)
    return vault.write_note(rel, body, meta)


def verify(note_id: str, took_effect: bool, note: str | None = None) -> dict[str, Any]:
    """追踪该纠正是否真的改变了后续行为。"""
    # 骨架：按 note_id 前缀回填状态；完整版将实现 markdown 原地更新
    status = "verified" if took_effect else "superseded"
    return {"note_id": note_id, "status": status, "note": note or ""}


def check(query: str | None = None, top_k: int = 5) -> list[dict[str, Any]]:
    """开工前检查历史纠正+教训（合并 corrections 与 lessons 两库）。"""
    hits = vault.search(query, top_k=top_k) if (query or "").strip() else vault.recent(top_k=top_k)
    return [h for h in hits if h["kind"] in {"correction", "lesson"}]
