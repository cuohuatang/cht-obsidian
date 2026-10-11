"""存储层测试：vault 初始化、markdown frontmatter、FTS5 检索、路径防护。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cut_bicuo_zjflow_mcp import config
from cut_bicuo_zjflow_mcp.storage import vault


@pytest.fixture()
def tmp_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "vault"
    monkeypatch.setattr(vault, "VAULT_PATH", root)
    monkeypatch.setattr(config, "VAULT_PATH", root)
    monkeypatch.setattr(vault, "INDEX_PATH", tmp_path / "index.sqlite")
    monkeypatch.setattr(config, "INDEX_PATH", tmp_path / "index.sqlite")
    vault.init_vault()
    return root


def test_init_creates_dirs(tmp_vault: Path) -> None:
    for sub in config.VAULT_DIRS.values():
        assert (tmp_vault / sub).is_dir()


def test_write_read_roundtrip(tmp_vault: Path) -> None:
    rel = f"{config.VAULT_DIRS['lessons']}/demo.md"
    vault.write_note(rel, "别把 RSI 搞反方向", {"title": "RSI 方向", "type": "lesson", "tags": ["qmt", "rsi"]})
    note = vault.read_note(rel)
    assert note["meta"]["type"] == "lesson"
    assert "RSI" in note["content"]


def test_overwrite_guard(tmp_vault: Path) -> None:
    rel = f"{config.VAULT_DIRS['memory']}/2026-10-09.md"
    vault.write_note(rel, "a", {"title": "a"})
    with pytest.raises(FileExistsError):
        vault.write_note(rel, "b", {"title": "b"})


def test_fts5_search_chinese(tmp_vault: Path) -> None:
    vault.write_note(
        f"{config.VAULT_DIRS['memory']}/2026-10-09.md",
        "QMT连接报错：需要重启行情服务",
        {"title": "QMT 报错", "type": "memory", "tags": ["qmt"]},
        overwrite=True,
    )
    # 中文短语、英文词、双字词均应命中（jieba 分词后 FTS5）
    for q in ["QMT", "报错", "QMT 报错", "行情"]:
        hits = vault.search(q, kind="memory", top_k=5)
        assert hits, f"query 未命中: {q!r}"
        assert hits[0]["title"] == "QMT 报错"


def test_path_traversal_blocked(tmp_vault: Path) -> None:
    with pytest.raises(ValueError):
        vault.write_note("../../etc/evil.md", "x", {})


def test_index_rebuild(tmp_vault: Path) -> None:
    vault.write_note(
        f"{config.VAULT_DIRS['lessons']}/a.md",
        "lesson body",
        {"title": "A", "type": "lesson", "tags": ["x"]},
    )
    vault.INDEX_PATH.unlink(missing_ok=True)
    result = vault.rebuild_index()
    assert result["indexed"] >= 1
    assert vault.search("lesson", top_k=5)


def test_hybrid_search_vector_complement(tmp_vault: Path) -> None:
    """纯 BM25 查不到（无共同文档），向量加权后能召回相关文档。"""
    vault.write_note(
        f"{config.VAULT_DIRS['memory']}/a.md",
        "QMT 报错 连接",
        {"title": "A", "type": "memory", "tags": ["qmt"]},
        overwrite=True,
    )
    vault.write_note(
        f"{config.VAULT_DIRS['memory']}/b.md",
        "行情 服务 重启",
        {"title": "B", "type": "memory", "tags": ["行情"]},
        overwrite=True,
    )
    # FTS5 隐式 AND："QMT" 与 "服务" 无共同文档 → BM25 空
    assert vault.search("QMT 服务", kind="memory", top_k=5, hybrid=False) == []
    hits = vault.search("QMT 服务", kind="memory", top_k=5, hybrid=True)
    assert hits, "向量加权应召回相关文档"
    expected = {f"{config.VAULT_DIRS['memory']}/a.md", f"{config.VAULT_DIRS['memory']}/b.md"}
    assert {h["note_id"] for h in hits} == expected
    assert any(h["method"] in {"hybrid", "vector"} for h in hits)


def test_lesson_backlink(tmp_vault: Path) -> None:
    """双链约定：踩坑本条目带 [[双链]] 回源并落盘。"""
    from cut_bicuo_zjflow_mcp.modules import lessons

    r = lessons.add("别把 RSI 搞反方向", tags=["qmt"], links=["01-流水账/2026-10-09", "02-踩坑本/其他"])
    assert r["path"].endswith(".md")
    note = vault.read_note(r["path"])
    assert "[[01-流水账/2026-10-09]]" in note["content"]
    assert "[[02-踩坑本/其他]]" in note["content"]
