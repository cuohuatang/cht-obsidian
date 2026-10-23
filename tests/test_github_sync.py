"""V0.3 GitHub 私有仓库同步测试：本地 bare 仓库模拟远端，验证 setup/push/status/脱敏。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cut_obsidian_mcp import config
from cut_obsidian_mcp.modules import github_sync
from cut_obsidian_mcp.storage import vault

FAKE_TOKEN = "ghp_TEST_TOKEN_123456"


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """隔离环境：vault + 本地 bare 远端 + config.json 落到 tmp。"""
    root = tmp_path / "vault"
    remote = tmp_path / "remote.git"
    monkeypatch.setattr(vault, "VAULT_PATH", root)
    monkeypatch.setattr(vault, "INDEX_PATH", tmp_path / "index.sqlite")
    monkeypatch.setattr(config, "VAULT_PATH", root)
    monkeypatch.setattr(config, "INDEX_PATH", tmp_path / "index.sqlite")
    monkeypatch.setattr(config, "APP_DIR", tmp_path / "app")
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "app" / "config.json")
    vault.init_vault()
    subprocess.run(["git", "init", "--bare", str(remote)], capture_output=True, check=True)
    return root, remote


def test_setup_and_push_roundtrip(env: tuple[Path, Path]) -> None:
    root, remote = env
    setup = github_sync.setup(repo=str(remote), token=FAKE_TOKEN, branch="main")
    assert setup["repo"] == str(remote)
    assert "token" not in " ".join(map(str, setup.values())) or FAKE_TOKEN not in str(setup)
    # 写入一条笔记后 push
    vault.write_note(
        "01-流水账/2026-10-23-000001.md",
        "测试：云端同步内容",
        {"note_id": "mem-sync-1", "title": "同步测试", "type": "memory", "tags": ["测试"], "agent": "claude-code"},
    )
    result = github_sync.push(message="V0.3 同步测试")
    assert result["pushed"] is True
    assert result["changed_files"] >= 1
    # 远端 bare 应有 commit（git init --bare 默认 HEAD 可能是 master，用 --all 覆盖）
    head = subprocess.run(
        ["git", "log", "--all", "--oneline", "-1"], cwd=remote, capture_output=True, text=True, check=False
    ).stdout
    assert head.strip(), "远端应存在首个 commit"
    # 二次 push 无变更 → 跳过
    again = github_sync.push()
    assert again["pushed"] is False


def test_status_after_push(env: tuple[Path, Path]) -> None:
    root, remote = env
    github_sync.setup(repo=str(remote), token=FAKE_TOKEN)
    vault.write_note(
        "01-流水账/2026-10-23-000002.md",
        "第二条同步内容",
        {"note_id": "mem-sync-2", "title": "同步二", "type": "memory", "tags": [], "agent": "codex"},
    )
    github_sync.push(message="status 测试")
    st = github_sync.status()
    assert st["repo"] == str(remote)
    assert st["local_changes"] == 0
    assert st["has_remote"] is True
    assert FAKE_TOKEN not in str(st), "status 不得泄漏 token"
    # 再写一条 → local_changes=1
    vault.write_note(
        "01-流水账/2026-10-23-000003.md",
        "未推送内容",
        {"note_id": "mem-sync-3", "title": "未推送", "type": "memory", "tags": [], "agent": "codex"},
    )
    st2 = github_sync.status()
    assert st2["local_changes"] == 1


def test_redact_never_leaks_token(env: tuple[Path, Path]) -> None:
    cred = {"token": FAKE_TOKEN}
    assert FAKE_TOKEN not in github_sync._redact(f"错误信息含 {FAKE_TOKEN} 结尾", cred)  # noqa: SLF001
    assert "***" in github_sync._redact(f"错误信息含 {FAKE_TOKEN}", cred)  # noqa: SLF001
