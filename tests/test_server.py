"""服务器骨架测试：34 个工具全部注册（V0.6）。"""

from __future__ import annotations

import asyncio

from cut_obsidian_mcp.server import mcp


def test_all_tools_registered() -> None:
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    expected = {
        # V0.2 基础 18 工具
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
        # V0.3 GitHub 同步 4 工具
        "cm_github_setup",
        "cm_github_push",
        "cm_github_pull",
        "cm_github_status",
        # V0.3 第二大脑 4 工具
        "cm_brain_process",
        "cm_brain_finalize",
        "cm_brain_moc",
        "cm_brain_status",
        # V0.6 自体检 + Harness² 嫁接 8 工具
        "cm_doctor",
        "cm_harness2_doctor",
        "cm_harness2_demo",
        "cm_harness2_setup",
        "cm_harness2_check",
        "cm_harness2_run",
        "cm_harness2_judge",
        "cm_harness2_report",
    }
    assert expected <= names, f"缺失工具: {expected - names}"
    assert len(names) == 34, f"工具总数应为 34，实际 {len(names)}：{sorted(names)}"


def test_usage_resource_registered() -> None:
    uris = {str(r.uri) for r in asyncio.run(mcp.list_resources())}
    assert "harness2://usage" in uris


def test_instructions_include_standing_orders() -> None:
    assert "STANDING ORDERS" in (mcp.instructions or "")
    assert "cm_harness2_run" in (mcp.instructions or "")
