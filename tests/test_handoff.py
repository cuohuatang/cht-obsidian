"""交接模块测试：六段式交接文档 + 未答问题转交 + 直接接手。"""

from __future__ import annotations

from pathlib import Path

import pytest

from cut_bicuo_zjflow_mcp import config
from cut_bicuo_zjflow_mcp.modules import handoff
from cut_bicuo_zjflow_mcp.storage import vault


@pytest.fixture()
def tmp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vault, "VAULT_PATH", tmp_path / "vault")
    monkeypatch.setattr(config, "VAULT_PATH", tmp_path / "vault")
    monkeypatch.setattr(vault, "INDEX_PATH", tmp_path / "index.sqlite")
    monkeypatch.setattr(config, "INDEX_PATH", tmp_path / "index.sqlite")
    vault.init_vault()


def test_handoff_create_resume_direct(tmp_env) -> None:
    r = handoff.create(
        task_overview="把 QMT 策略迁移到新网关",
        current_state="已完成回测，年化 35%，待接入实盘",
        important_discoveries="网关 8082 端口需先启动",
        next_steps="接入实盘前先跑 1 周纸面",
        from_agent="Claude Code",
        to_agent="Codex",
    )
    assert r["path"].endswith(".md")
    resumed = handoff.resume(r["path"].rsplit("/", 1)[-1][:16])
    assert resumed["must_answer"] is False
    assert "直接接手" in resumed["instruction"]


def test_handoff_unanswered_question_forwarded(tmp_env) -> None:
    r = handoff.create(
        task_overview="整理合同模板",
        current_state="已列 5 个条款",
        unanswered_question="违约金比例用 20% 还是 30%？",
        from_agent="Cursor",
    )
    resumed = handoff.resume(r["path"].rsplit("/", 1)[-1][:16])
    assert resumed["must_answer"] is True
    assert "违约金" in resumed["question"]
