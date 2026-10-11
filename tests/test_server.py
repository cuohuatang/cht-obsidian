"""服务器骨架测试：18 个工具全部注册（V0.2）。"""

from __future__ import annotations

import asyncio

from cut_bicuo_zjflow_mcp.server import mcp


def test_all_tools_registered() -> None:
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    expected = {
        "cm_memory_save",
        "cm_memory_recall",
        "cm_memory_search",
        "cm_summarize",
        "cm_summary_weekly",
        "cm_lesson_add",
        "cm_lesson_inject",
        "cm_correction_log",
        "cm_correction_verify",
        "cm_correction_check",
        "cm_vault_init",
        "cm_obsidian_read",
        "cm_obsidian_write",
        "cm_handoff_create",
        "cm_handoff_list",
        "cm_handoff_resume",
        "cm_skill_suggest",
        "cm_skill_propose",
    }
    assert expected <= names, f"缺失工具: {expected - names}"
