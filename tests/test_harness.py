"""V0.6 Harness² 嫁接模块测试：CLI 包装机制 + 缺失降级 + 自体检 + 手册资源。"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from cut_obsidian_mcp import config
from cut_obsidian_mcp.modules import harness
from cut_obsidian_mcp.storage import vault


@pytest.fixture()
def tmp_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "vault"
    monkeypatch.setattr(vault, "VAULT_PATH", root)
    monkeypatch.setattr(vault, "INDEX_PATH", tmp_path / "index.sqlite")
    monkeypatch.setattr(config, "VAULT_PATH", root)
    monkeypatch.setattr(config, "INDEX_PATH", tmp_path / "index.sqlite")
    # CONFIG_FILE 必须隔离到 tmp，否则自体检会读写真实用户凭证文件
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    vault.init_vault()
    return root


@pytest.fixture
def stub_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """造 6 个 stub CLI，模拟 Harness² 已安装的环境。"""
    d = tmp_path / "stubbin"
    d.mkdir()
    for name in harness._COMMANDS.values():
        f = d / name
        f.write_text(f'#!/bin/sh\necho "[stub] {name} $@"\n', encoding="utf-8")
        f.chmod(0o755)
    monkeypatch.setenv("PATH", str(d) + os.pathsep + os.environ.get("PATH", ""))
    # 清掉逐个覆盖变量，确保走 PATH 解析
    for key in harness._COMMANDS:
        monkeypatch.delenv("HARNESS2_CMD_" + key.upper(), raising=False)
    return d


# ---------- _flag：空值跳过 ----------

def test_flag_skips_empty_values() -> None:
    args: list = []
    harness._flag(args, "--subset", None)
    harness._flag(args, "--dry-run", False)
    harness._flag(args, "--only-domains", "")
    assert args == []
    harness._flag(args, "--k", 2)
    harness._flag(args, "--dry-run", True)
    assert args == ["--k", 2, "--dry-run"]


# ---------- _resolve：PATH / 环境变量覆盖 ----------

def test_resolve_prefers_env_override(stub_bin: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARNESS2_CMD_RUN", "/custom/harness2")
    assert harness._resolve("run") == "/custom/harness2"


def test_resolve_finds_stub_in_path(stub_bin: Path) -> None:
    for key in harness._COMMANDS:
        assert harness._resolve(key) == str(stub_bin / harness._COMMANDS[key])


def test_resolve_none_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    for key in harness._COMMANDS:
        monkeypatch.delenv("HARNESS2_CMD_" + key.upper(), raising=False)
    assert harness._resolve("run") is None


# ---------- _run：缺失降级 / stub 转发 ----------

def test_run_returns_install_hint_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    for key in harness._COMMANDS:
        monkeypatch.delenv("HARNESS2_CMD_" + key.upper(), raising=False)
    out = harness._run("run", ["--bench", "lab"], 30, None)
    assert out.startswith("[error] ")
    assert "git clone https://github.com/google-research/harness2.git" in out


def test_run_forwards_to_stub(stub_bin: Path) -> None:
    out = harness._run("demo", ["--output", "runs/demo", "--k", 2], 30, None)
    assert "exit=0" in out
    assert "[stub] harness2-demo --output runs/demo --k 2" in out


def test_run_workdir_env(stub_bin: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    wd = tmp_path / "h2root"
    wd.mkdir()
    monkeypatch.setenv("HARNESS2_CWD", str(wd))
    assert harness._workdir(None) == str(wd)
    assert harness._workdir("/explicit") == "/explicit"


# ---------- doctor：已安装 / 未安装两种结论 ----------

def test_doctor_reports_ready(stub_bin: Path) -> None:
    out = harness.doctor()
    assert "结论：CLI 已就绪" in out
    assert "缺失" not in out


def test_doctor_reports_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    for key in harness._COMMANDS:
        monkeypatch.delenv("HARNESS2_CMD_" + key.upper(), raising=False)
    out = harness.doctor()
    assert "结论：未安装或不完整" in out
    assert "INSTALL" not in out  # 提示走 INSTALL_HINT 文案而非裸关键字


# ---------- 参数一致性：judge/report 与 run 同参 ----------

def test_judge_and_run_share_param_names() -> None:
    """judge/report 必须接受与 run 相同的 bench/subset/k/mode/substrate/seed。"""
    import inspect
    run_params = set(inspect.signature(harness.run).parameters)
    judge_params = set(inspect.signature(harness.judge).parameters)
    report_params = set(inspect.signature(harness.report).parameters)
    shared = {"bench", "k", "mode", "substrate", "subset", "seed"}
    assert shared <= run_params and shared <= judge_params
    # report 与上游一致不接受 seed（汇总多次 sweep 的 k 列表）
    assert (shared - {"seed"}) <= report_params


# ---------- usage 手册资源 ----------

def test_usage_text_returns_manual() -> None:
    text = harness.usage_text()
    assert "Propose–Probe–Compose" in text
    assert "cm_harness2_run" in text
    assert "dry-run" in text.lower()


# ---------- self_doctor：cht-obsidian 自体检 ----------

def test_self_doctor_healthy_vault(tmp_vault: Path) -> None:
    r = harness.self_doctor()
    assert r["level"] in ("ok", "warn")  # 无 GitHub 配置时报 warn，不报 error
    names = {c["name"] for c in r["checks"]}
    assert {"version", "vault_writable", "config_perm", "git", "index", "github_sync", "harness2_cli"} <= names
    assert r["summary"].endswith("项就绪")


def test_self_doctor_flags_bad_config_perm(tmp_vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """config.json 权限过于开放时应被判为 error 级。"""
    cfg = harness.config.CONFIG_FILE
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text('{"repo":"a/b","token":"ghp_x"}', encoding="utf-8")
    cfg.chmod(0o644)
    r = harness.self_doctor()
    perm = next(c for c in r["checks"] if c["name"] == "config_perm")
    assert perm["ok"] is False
    assert r["level"] == "error"


def test_self_doctor_flags_repo_without_credential(tmp_vault: Path) -> None:
    cfg = harness.config.CONFIG_FILE
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text('{"repo":"a/b"}', encoding="utf-8")
    cfg.chmod(0o600)
    r = harness.self_doctor()
    sync = next(c for c in r["checks"] if c["name"] == "github_sync")
    assert sync["ok"] is False
    assert "无推送凭证" in sync["detail"]
    assert any("cm_github_setup" in a for a in r["advice"])


def test_self_doctor_ok_with_token(tmp_vault: Path) -> None:
    cfg = harness.config.CONFIG_FILE
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text('{"repo":"a/b","token":"ghp_xxx"}', encoding="utf-8")
    cfg.chmod(0o600)
    r = harness.self_doctor()
    sync = next(c for c in r["checks"] if c["name"] == "github_sync")
    assert sync["ok"] is True
