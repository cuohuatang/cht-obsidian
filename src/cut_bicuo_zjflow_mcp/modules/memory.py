"""① 自动记忆模块（源自 agentmemory 设计）：会话记录 + 上下文召回。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from ..config import VAULT_DIRS
from ..storage import vault

_KIND = "memory"


def save(content: str, title: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    """记录一次会话事实/上下文，写入 01-流水账（每条独立文件，不覆盖历史）。"""
    title = title or content.strip().splitlines()[0][:40]
    note_id = f"mem-{uuid.uuid4().hex[:12]}"
    rel = f"{VAULT_DIRS['memory']}/{datetime.now().strftime('%Y-%m-%d-%H%M%S')}-{note_id[4:10]}.md"
    meta = {
        "note_id": note_id,
        "title": title,
        "type": _KIND,
        "tags": tags or [],
        "model": "any",
    }
    return vault.write_note(rel, content, meta, overwrite=False)


def recall(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """开工前召回相关历史记忆（BM25）。"""
    return vault.search(query, kind=_KIND, top_k=top_k)


def search(query: str, top_k: int = 10) -> list[dict[str, Any]]:
    """全库混合搜索（v0 为 FTS5 BM25；后续可接本地向量）。"""
    return vault.search(query, kind=_KIND, top_k=top_k)
