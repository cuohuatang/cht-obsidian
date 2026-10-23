"""V0.3 第二大脑模块测试：消化管线（提炼→工作流→打标签→双链→MOC）。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from cut_obsidian_mcp import config
from cut_obsidian_mcp.modules import brain
from cut_obsidian_mcp.storage import vault


@pytest.fixture()
def tmp_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "vault"
    monkeypatch.setattr(vault, "VAULT_PATH", root)
    monkeypatch.setattr(vault, "INDEX_PATH", tmp_path / "index.sqlite")
    monkeypatch.setattr(config, "VAULT_PATH", root)
    monkeypatch.setattr(config, "INDEX_PATH", tmp_path / "index.sqlite")
    vault.init_vault()
    return root


def _seed_memory(tmp_vault: Path, content: str, tag: str, agent: str = "claude-code") -> None:
    note_id = f"mem-seed-{abs(hash(content)) % 10**6}"
    vault.write_note(
        f"{config.VAULT_DIRS['memory']}/{datetime.now().strftime('%Y-%m-%d-%H%M%S')}-{note_id[-6:]}.md",
        content,
        {
            "note_id": note_id,
            "title": content[:20],
            "type": "memory",
            "tags": [tag],
            "agent": agent,
            "category": "测试项目",
        },
    )


def test_process_creates_workflow_and_moc(tmp_vault: Path) -> None:
    _seed_memory(tmp_vault, "1. 执行部署脚本\n2. 检查健康检查接口\n部署流程记录", "部署")
    _seed_memory(tmp_vault, "pip install -e . 之后要重跑 pytest\n安装注意事项", "部署")
    result = brain.process(agent="claude-code", since_days=7)
    assert result["processed"] == 2
    assert result["clusters"] >= 1
    assert result["workflow_pages"], "应生成工作流页"
    assert result["moc"].endswith("MOC.md")
    # 工作流页 frontmatter 字段齐全（宪法规范）
    wf_rel = result["workflow_pages"][0]
    note = vault.read_note(wf_rel)
    meta = note["meta"]
    for field in ("type", "category", "status", "confidence", "knowledge_expire_date", "source", "tags"):
        assert field in meta, f"frontmatter 缺 {field}"
    assert meta["type"] == "workflow"
    assert meta["status"] in {"draft", "verified"}
    assert meta["knowledge_expire_date"] > datetime.now().strftime("%Y-%m-%d")
    # 页内双链回源
    assert "[[01-流水账" in note["content"] or "[[" in note["content"]
    # 原始素材被打"已消化"标签
    processed = [c["meta"] for c in brain._collect_candidates(7, "claude-code")]  # noqa: SLF001
    assert processed == [], "素材应已被标记为已消化"


def test_process_no_candidates(tmp_vault: Path) -> None:
    result = brain.process(since_days=7)
    assert result["processed"] == 0
    assert result["workflow_pages"] == []


def test_process_agent_isolation(tmp_vault: Path) -> None:
    _seed_memory(tmp_vault, "A 的专属记录内容", "主题A", agent="agent-a")
    _seed_memory(tmp_vault, "B 的专属记录内容", "主题B", agent="agent-b")
    result_a = brain.process(agent="agent-a", since_days=7)
    assert result_a["processed"] == 1
    assert result_a["workflow_pages"][0].startswith("04-经验总结")
    # MOC 只含 agent-a 的工作流
    moc = vault.read_note(result_a["moc"])
    assert "主题A" in moc["content"]
    assert "主题B" not in moc["content"]


def test_finalize_without_push(tmp_vault: Path) -> None:
    _seed_memory(tmp_vault, "会话事实：今天完成设计评审", "评审")
    result = brain.finalize(agent="claude-code", push=False)
    assert "summary" in result
    assert "skill_suggest" in result
    assert result["brain_process"]["processed"] >= 1


def test_moc_aggregates_by_category(tmp_vault: Path) -> None:
    _seed_memory(tmp_vault, "流程一：git 提交后打 tag", "发布")
    _seed_memory(tmp_vault, "流程二：docker 构建并推送", "发布")
    brain.process(agent="claude-code", since_days=7)
    moc_rel = brain._moc("claude-code")  # noqa: SLF001
    moc = vault.read_note(moc_rel)
    assert "## 发布" in moc["content"]
    assert "[[04-经验总结" in moc["content"]


def test_status_counts(tmp_vault: Path) -> None:
    _seed_memory(tmp_vault, "一条流水", "通用")
    st = brain.status()
    assert st["workflow_pages"] >= 0
    assert st["pending_digest"] == 1
    assert "notes_by_dir" in st
