"""技能沉淀模块测试：重复工作流挖掘 + 自动提示 + 从历史记录真实提炼 SKILL 草稿。"""

from __future__ import annotations

from pathlib import Path

import pytest

from cut_obsidian_mcp import config
from cut_obsidian_mcp.modules import skillcraft
from cut_obsidian_mcp.storage import vault


@pytest.fixture()
def tmp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vault, "VAULT_PATH", tmp_path / "vault")
    monkeypatch.setattr(config, "VAULT_PATH", tmp_path / "vault")
    monkeypatch.setattr(vault, "INDEX_PATH", tmp_path / "index.sqlite")
    monkeypatch.setattr(config, "INDEX_PATH", tmp_path / "index.sqlite")
    vault.init_vault()


def test_suggest_detects_repeated_workflow(tmp_env) -> None:
    for i in range(3):
        vault.write_note(
            f"{config.VAULT_DIRS['memory']}/2026-10-0{i+1}.md",
            f"发布小红书笔记 {i}",
            {"title": f"小红书发布 {i}", "type": "memory", "tags": ["小红书发布", "内容"]},
        )
    result = skillcraft.suggest(top_k=30)
    assert result["suggestions"]
    assert result["suggestions"][0]["workflow"] == "小红书发布"
    assert "一个 skill 吗" in result["prompt"]


def test_propose_extracts_real_steps_from_history(tmp_env) -> None:
    """V0.2 核心：propose 从历史记录真实提炼工作流步骤，而非空模板。"""
    vault.write_note(
        f"{config.VAULT_DIRS['memory']}/publish.md",
        "发布小红书笔记流程：\n1. 确认标题与封面图\n2. 调用 cm_summarize 提炼正文\n3. 检查话题标签\n4. 执行发布",
        {"title": "小红书发布流程", "type": "memory", "tags": ["小红书发布"]},
        overwrite=True,
    )
    vault.write_note(
        f"{config.VAULT_DIRS['lessons']}/pitfall.md",
        "## 教训\n封面图尺寸必须 3:4，否则被压缩",
        {"title": "封面尺寸", "type": "lesson", "tags": ["小红书发布"]},
    )
    result = skillcraft.propose("发布小红书笔记", tags=["小红书发布"])
    assert result["evidence_count"] >= 1
    assert result["extracted_steps"] >= 3, "应从历史记录提炼出真实步骤"
    draft = result["sk_md_draft"]
    assert "工作流（从历史记录静默提炼）" in draft
    assert "确认标题与封面图" in draft
    assert "封面图尺寸必须 3:4" in draft  # 教训提炼进规则
    assert "[[" in draft  # 来源双链
    assert "未写盘" in result["note"]
