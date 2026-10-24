"""③ 踩坑本模块（errlore 式）：文件式教训 + 按模型信任度 + 开工前注入。"""

from __future__ import annotations

import uuid
from typing import Any

from ..config import VAULT_DIRS
from ..storage import vault

_KIND = "lesson"


def add(
    lesson: str,
    tags: list[str] | None = None,
    model: str | None = None,
    severity: str = "medium",
    links: list[str] | None = None,
    agent: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """文件式记录一条教训到 02-踩坑本。

    links：Obsidian 双链回源列表（如 ["01-流水账/2026-10-09", "02-踩坑本/其他教训"]），
    渲染为正文底部 [[双链]]，与 Obsidian 图谱互通（双链约定，见 DESIGN.md）。
    agent / category：来源智能体与分类项目（第二大脑按 Agent 分空间）。
    """
    note_id = f"les-{uuid.uuid4().hex[:12]}"
    title = lesson.strip().splitlines()[0][:40]
    rel = f"{VAULT_DIRS['lessons']}/{vault.slugify(title)}-{note_id[-6:]}.md"
    meta = {
        "note_id": note_id,
        "title": title,
        "type": _KIND,
        "tags": tags or [],
        "model": model or "any",  # errlore 式：针对哪个模型的信任度
        "severity": severity,
        "links": links or [],
        "agent": agent,
        "category": category,
    }
    body = f"## 教训\n{lesson}\n\n## 触发场景\n（待补充 evidence）"
    if links:
        rl = vault.resolve_links(links)  # 双链自动修正：短名 → 真实文件路径
        meta["links"] = rl["resolved"]
        body += "\n\n## 相关笔记\n" + "\n".join(f"- [[{l}]]" for l in rl["resolved"])
        if rl["unresolved"]:
            body += "\n\n> ⚠️ 以下链接未能匹配库内文件，已原样保留：\n> " + "\n> ".join(rl["unresolved"])
    return vault.write_note(rel, body, meta)


def inject(query: str, top_k: int = 3) -> dict[str, Any]:
    """开工前注入：返回相关教训的现成上下文文本块（含模型标注）。"""
    hits = vault.search(query, kind=_KIND, top_k=top_k)
    block = (
        "【已知教训 · cut-obsidian 踩坑本】\n"
        + "\n".join(f"- [{h['title']}] (模型:{h['model']} 相关度:{h['score']})" for h in hits)
        if hits
        else "【已知教训】无相关记录"
    )
    return {"injected": hits, "context_block": block}
