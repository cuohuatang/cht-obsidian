"""V0.4 增强测试：双链自动修正（vault.resolve_links）+ 语义聚类（brain TF-IDF 余弦）。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from cut_obsidian_mcp import config
from cut_obsidian_mcp.modules import brain, lessons
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


# ---------- 双链自动修正 ----------

def test_resolve_exact_hit(tmp_vault: Path) -> None:
    rel = f"{config.VAULT_DIRS['memory']}/2026-10-24-demo.md"
    vault.write_note(rel, "内容", {"title": "demo", "type": "memory", "tags": []})
    out = vault.resolve_links([rel[:-3], rel])
    assert out["resolved"] == [rel[:-3], rel[:-3]]
    assert out["unresolved"] == []


def test_resolve_stem_match(tmp_vault: Path) -> None:
    """核心场景：README 式短名自动补全为真实带后缀文件名。"""
    real = f"{config.VAULT_DIRS['memory']}/2026-10-24-163607-03b2f2.md"
    vault.write_note(real, "内容", {"title": "流水", "type": "memory", "tags": []})
    out = vault.resolve_links([f"{config.VAULT_DIRS['memory']}/2026-10-24"])
    assert out["resolved"] == [real[:-3]]
    assert out["unresolved"] == []


def test_resolve_slug_normalized_match(tmp_vault: Path) -> None:
    vault.write_note(f"{config.VAULT_DIRS['memory']}/docker部署指南-01a2.md", "x", {"title": "t", "type": "memory", "tags": []})
    out = vault.resolve_links(["docker_部署 指南"])
    assert out["resolved"] == [f"{config.VAULT_DIRS['memory']}/docker部署指南-01a2"]
    assert out["unresolved"] == []


def test_resolve_ambiguous_keeps_original(tmp_vault: Path) -> None:
    """两个候选都命中子串 → 不猜，原样保留并报告。"""
    d = config.VAULT_DIRS["memory"]
    vault.write_note(f"{d}/qmt-下单-aa.md", "x", {"title": "t", "type": "memory", "tags": []})
    vault.write_note(f"{d}/qmt-下单重试-bb.md", "x", {"title": "t", "type": "memory", "tags": []})
    out = vault.resolve_links(["qmt-下单"])
    assert out["resolved"] == ["qmt-下单"]
    assert out["unresolved"] == ["qmt-下单"]


def test_resolve_no_match_reports_unresolved(tmp_vault: Path) -> None:
    out = vault.resolve_links(["不存在的笔记"])
    assert out["resolved"] == ["不存在的笔记"]
    assert out["unresolved"] == ["不存在的笔记"]


def test_lesson_add_auto_fixes_links(tmp_vault: Path) -> None:
    real = f"{config.VAULT_DIRS['memory']}/2026-10-24-120000-ab12cd.md"
    vault.write_note(real, "原始记忆", {"title": "m", "type": "memory", "tags": []})
    lessons.add("教训内容", links=[f"{config.VAULT_DIRS['memory']}/2026-10-24"])
    files = [p for p in (tmp_vault / config.VAULT_DIRS["lessons"]).glob("*.md")]
    body = files[0].read_text(encoding="utf-8")
    assert f"[[{real[:-3]}]]" in body
    assert "⚠️" not in body


def test_lesson_add_marks_unresolved(tmp_vault: Path) -> None:
    lessons.add("教训内容", links=["完全没有的笔记"])
    files = list((tmp_vault / config.VAULT_DIRS["lessons"]).glob("*.md"))
    body = files[0].read_text(encoding="utf-8")
    assert "完全没有的笔记" in body
    assert "⚠️" in body


# ---------- 语义聚类 ----------

def _seed(tmp_vault: Path, content: str, tags: list[str]) -> None:
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S-%f")
    vault.write_note(
        f"{config.VAULT_DIRS['memory']}/{ts}.md",
        content,
        {"title": content[:20], "type": "memory", "tags": tags, "updated": datetime.now().isoformat()},
    )


def test_semantic_clusters_similar_content_without_shared_tags(tmp_vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """无共同标签、内容高度相似 → 应被语义聚类合并到一簇。"""
    _seed(tmp_vault, "用 docker compose 部署服务，先 build 镜像再 up -d 启动容器，端口映射到宿主机", [])
    _seed(tmp_vault, "docker compose 部署应用：构建镜像后 docker compose up -d 启动，注意端口映射配置", [])
    _seed(tmp_vault, "今天天气不错适合出去跑步锻炼身体保持健康作息", [])
    monkeypatch.setenv("CUT_OBSIDIAN_SEMANTIC_THRESHOLD", "0.30")
    clusters = brain._cluster(brain._collect_candidates(since_days=7, agent=None))
    sizes = sorted((len(c) for c in clusters), reverse=True)
    assert sizes[0] == 2  # 两条 docker 部署笔记聚到一起


def test_semantic_keeps_dissimilar_notes_apart(tmp_vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed(tmp_vault, "用 docker compose 部署服务，构建镜像并启动容器映射端口", [])
    _seed(tmp_vault, "周末去菜市场买了西红柿鸡蛋和面条做晚饭", [])
    monkeypatch.setenv("CUT_OBSIDIAN_SEMANTIC_THRESHOLD", "0.30")
    clusters = brain._cluster(brain._collect_candidates(since_days=7, agent=None))
    assert len(clusters) == 2


def test_threshold_env_override(tmp_vault: Path) -> None:
    monkeypatch_fail = "abc"
    import os
    os.environ["CUT_OBSIDIAN_SEMANTIC_THRESHOLD"] = monkeypatch_fail
    assert brain._semantic_threshold() == 0.40  # 非法值回退默认
    del os.environ["CUT_OBSIDIAN_SEMANTIC_THRESHOLD"]


def test_cosine_helpers() -> None:
    assert brain._cosine({"a": 1.0}, {"b": 1.0}) == 0.0
    assert brain._cosine({}, {"a": 1.0}) == 0.0
    assert brain._cosine({"a": 1.0}, {"a": 2.0}) == pytest.approx(1.0)


# ---------- _remote_url owner/repo 修复（V0.4） ----------

def test_remote_url_owner_repo_builds_https(tmp_vault: Path) -> None:
    from cut_obsidian_mcp.modules import github_sync
    url = github_sync._remote_url({"repo": "cuohuatang/brain", "token": "ghp_test123"})
    assert url == "https://x-access-token:ghp_test123@github.com/cuohuatang/brain.git"


def test_remote_url_passthrough(tmp_vault: Path) -> None:
    from cut_obsidian_mcp.modules import github_sync
    assert github_sync._remote_url({"repo": "git@github.com:a/b.git", "token": "t"}) == "git@github.com:a/b.git"
    assert github_sync._remote_url({"repo": "/tmp/local", "token": "t"}) == "/tmp/local"
