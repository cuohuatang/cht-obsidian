"""⑥ 会话交接模块（源自 squidllee/session-handoff 精华）：六段式交接 + 自动接手。

精华移植（不依赖 entire CLI，用 cut-obsidian 自身数据驱动）：
- 六段式交接结构：任务概览/当前状态/重要发现/下一步/需保留上下文/未回答问题
- 公告行标识来源 Agent；未回答问题必须转问用户、不得默认
- 无未答问题时，新 Agent 直接接手干活，不重复解释、不问许可
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from ..config import VAULT_DIRS
from ..storage import vault

_KIND = "handoff"

_SECTION_KEYS = (
    "task_overview",
    "current_state",
    "important_discoveries",
    "next_steps",
    "context_to_preserve",
    "unanswered_question",
)

_SECTION_TITLES = {
    "task_overview": "任务概览",
    "current_state": "当前状态",
    "important_discoveries": "重要发现",
    "next_steps": "下一步",
    "context_to_preserve": "需保留上下文",
    "unanswered_question": "未回答问题",
}


def create(
    task_overview: str,
    current_state: str,
    important_discoveries: str = "",
    next_steps: str = "",
    context_to_preserve: str = "",
    unanswered_question: str | None = None,
    from_agent: str | None = None,
    to_agent: str | None = None,
) -> dict[str, Any]:
    """把"上一个 Agent 干到哪"总结为六段式交接文档，写入 05-交接。"""
    note_id = f"hdo-{uuid.uuid4().hex[:12]}"
    title = task_overview.strip().splitlines()[0][:40]
    rel = f"{VAULT_DIRS['handoffs']}/{date.today().isoformat()}-{vault.slugify(title)}-{note_id[-6:]}.md"
    meta = {
        "note_id": note_id,
        "title": title,
        "type": _KIND,
        "status": "active",  # active → resumed
        "from_agent": from_agent or "any",
        "to_agent": to_agent or "any",
    }
    body = [f"# 交接：{title}"]
    if from_agent:
        body.append(f"> 来源会话：`{from_agent}` → 目标：`{to_agent or '任意 Agent'}`")
    for key in _SECTION_KEYS:
        text = unanswered_question if key == "unanswered_question" else locals().get(key, "")
        if key == "unanswered_question" and not text:
            continue  # 无未答问题时该节不出现
        if not text:
            continue  # 空节不填充（精华规则：不编造填充）
        body.append(f"## {_SECTION_TITLES[key]}\n{text}")
    result = vault.write_note(rel, "\n\n".join(body), meta)
    result["note_id"] = note_id
    return result


def list_handoffs(top_k: int = 10) -> list[dict[str, Any]]:
    """列出最近交接文档（按更新时间倒序）。"""
    return vault.recent(kind=_KIND, top_k=top_k)


def resume(handoff_id: str) -> dict[str, Any]:
    """新 Agent 接手：读取交接文档；有未答问题则转问，否则直接开干。"""
    # 匹配规则：note_id 前缀 或 文件名前缀（两者都接受）
    for rel, _ in vault._walk_vault():  # noqa: SLF001
        if VAULT_DIRS["handoffs"] not in rel:
            continue
        note = vault.read_note(rel)
        nid = note["meta"].get("note_id", "")
        if nid.startswith(handoff_id) or rel.rsplit("/", 1)[-1].startswith(handoff_id):
            question = note["meta"].get("unanswered_question", "")
            body = note["content"]
            if not question and "未回答问题" in body:
                question = body.split("未回答问题", 1)[-1].lstrip("：: \n").strip() or None
            if question:
                return {
                    "handoff_id": handoff_id,
                    "must_answer": True,
                    "question": question,
                    "instruction": "上一 Agent 向你提了问题但未获回答：请先回答该问题，再继续工作。",
                }
            return {
                "handoff_id": handoff_id,
                "must_answer": False,
                "instruction": "已读取交接文档，直接接手继续干活——任务/状态/下一步见交接正文，无需重新解释背景。",
                "content": body,
            }
    return {"handoff_id": handoff_id, "found": False, "instruction": "未找到该交接文档，请确认 handoff_id 或先 cm_handoff_list。"}
