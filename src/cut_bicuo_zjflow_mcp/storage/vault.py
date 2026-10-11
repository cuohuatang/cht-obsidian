"""存储层：vault markdown（frontmatter）+ SQLite FTS5 索引 + TF-IDF 向量。

真相源永远是 markdown 文件；SQLite 仅作 BM25 检索加速，可随时重建。
检索：默认 hybrid = BM25 + TF-IDF 向量余弦（纯本地，无外部模型、无 API key）。
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import jieba

from ..config import INDEX_PATH, VAULT_DIRS, VAULT_PATH

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.S)
# FTS5 MATCH 关键字需转义为普通词
_FTS_RESERVED = {"AND", "OR", "NOT", "NEAR"}


def utcnow() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def segment(text: str) -> str:
    """jieba 分词 + 过滤非字母数字 token，供 FTS5 索引/查询使用。"""
    tokens = []
    for w in jieba.lcut(text):
        w = w.strip()
        if not w:
            continue
        if not re.fullmatch(r"[A-Za-z0-9\u4e00-\u9fff]+", w):
            continue
        if w.upper() in _FTS_RESERVED:
            w = f'"{w}"'
        tokens.append(w)
    return " ".join(tokens)


def slugify(text: str, max_len: int = 60) -> str:
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text).strip("-")
    return text[:max_len] or uuid.uuid4().hex[:8]


def _ensure_vault() -> Path:
    VAULT_PATH.mkdir(parents=True, exist_ok=True)
    for sub in VAULT_DIRS.values():
        (VAULT_PATH / sub).mkdir(parents=True, exist_ok=True)
    return VAULT_PATH


def _connect() -> sqlite3.Connection:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(INDEX_PATH)
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS notes USING fts5(
          note_id, title, content, tags, model, kind, updated_at,
          tokenize='unicode61'
        )
        """
    )
    return conn


def _resolve(relative: str) -> Path:
    """解析 vault 相对路径，禁止越出 vault 根（防路径穿越）。"""
    raw = (VAULT_PATH / relative).resolve()
    root = VAULT_PATH.resolve()
    if not raw.is_relative_to(root):
        raise ValueError(f"路径越出 vault 根目录: {relative}")
    return raw


def init_vault(path: str | None = None) -> dict[str, Any]:
    """幂等初始化 vault 目录 + 索引。"""
    if path:
        global VAULT_PATH  # noqa: PLW0603
        VAULT_PATH = Path(path)  # 运行时重定向（测试/自定义用）
    _reset_vec_cache()
    created = _ensure_vault()
    _connect().close()
    return {"vault_path": str(created), "created_dirs": list(VAULT_DIRS.values())}


def read_note(relative: str) -> dict[str, Any]:
    p = _resolve(relative)
    if not p.is_file():
        raise FileNotFoundError(f"note 不存在: {relative}")
    raw = p.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(raw)
    meta: dict[str, Any] = {}
    body = raw
    if m:
        try:
            meta = json.loads(m.group(1))
        except json.JSONDecodeError:
            meta = {"_parse": "frontmatter 非 JSON，按原样保留"}
        body = raw[m.end():].lstrip("\n")
    return {"path": str(p), "meta": meta, "content": body}


def read_note_by_id(note_id: str) -> dict[str, Any] | None:
    """按 note_id 或相对路径读取 note（兼容 mem-/les-/cor-/hdo- 等 ID 与路径两种形式）。"""
    try:
        return read_note(note_id)
    except (FileNotFoundError, ValueError):
        pass
    for rel, _ in _walk_vault():
        try:
            note = read_note(rel)
        except Exception:  # noqa: BLE001
            continue
        if note["meta"].get("note_id") == note_id or rel.endswith(note_id):
            return note
    return None


def write_note(
    relative: str,
    content: str,
    meta: dict[str, Any] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """写 markdown（带 frontmatter 的 JSON 字段，Obsidian 兼容）。"""
    p = _resolve(relative)
    if p.exists() and not overwrite:
        raise FileExistsError(f"已存在且 overwrite=False: {relative}")
    p.parent.mkdir(parents=True, exist_ok=True)
    meta = dict(meta or {})
    meta.setdefault("created", utcnow())
    meta["updated"] = utcnow()
    front = json.dumps(meta, ensure_ascii=False, indent=2)
    p.write_text(f"---\n{front}\n---\n\n{content.strip()}\n", encoding="utf-8")
    _index(relative, meta, content)
    return {"path": str(p)}


def _index(relative: str, meta: dict[str, Any], content: str) -> None:
    note_id = meta.get("note_id") or relative
    conn = _connect()
    try:
        conn.execute("DELETE FROM notes WHERE note_id = ?", (note_id,))
        conn.execute(
            "INSERT INTO notes(note_id, title, content, tags, model, kind, updated_at) VALUES (?,?,?,?,?,?,?)",
            (
                note_id,
                meta.get("title", ""),
                segment(f"{meta.get('title', '')} {content}"),
                # tags 保持原样（不切词）：供聚类/过滤精确使用；全文命中走 content 列
                " ".join(meta.get("tags", [])),
                meta.get("model", ""),
                meta.get("type", ""),
                meta.get("updated", ""),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def recent(kind: str | None = None, top_k: int = 10) -> list[dict[str, Any]]:
    """按更新时间倒序取最近记录（用于空查询的开工检查）。"""
    conn = _connect()
    try:
        sql = "SELECT note_id, title, tags, model, kind, updated_at FROM notes"
        params: list[Any] = []
        if kind:
            sql += " WHERE kind = ?"
            params.append(kind)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(top_k)
        return [
            {
                "note_id": r[0],
                "title": r[1],
                "tags": (r[2] or "").split(),
                "model": r[3],
                "kind": r[4],
                "updated_at": r[5],
            }
            for r in conn.execute(sql, params).fetchall()
        ]
    finally:
        conn.close()


def search(query: str, kind: str | None = None, top_k: int = 10, hybrid: bool = True) -> list[dict[str, Any]]:
    """混合检索：BM25 + TF-IDF 向量余弦（归一化加权 0.5/0.5）。

    参数 hybrid=False 时退回纯 BM25（V0.1 默认 hybrid=True，v0.2 可加本地 LLM embedding 增强）。
    """
    bm25 = _bm25_search(query, kind, top_k)
    if not hybrid or len(_corpus()) < 2:
        return bm25
    vec = _tfidf_search(query, kind, top_k * 3)
    if not bm25:
        return vec[:top_k]
    if not vec:
        return bm25
    # BM25 score 归一化到 0~1（按本次结果 min-max）
    b_min = min(h["score"] for h in bm25)
    b_max = max(h["score"] for h in bm25)
    span = (b_max - b_min) or 1.0
    merged: dict[str, dict[str, Any]] = {}
    for h in bm25:
        rec = dict(h)
        rec["score"] = round(0.5 * (h["score"] - b_min) / span, 4)
        rec["method"] = "bm25"
        merged[h["note_id"]] = rec
    for v in vec:
        rec = merged.get(v["note_id"])
        if rec:
            rec["score"] = round(rec["score"] + 0.5 * v["score"], 4)
            rec["method"] = "hybrid"
        else:
            nv = dict(v)
            nv["score"] = round(0.5 * v["score"], 4)
            nv["method"] = "vector"
            merged[v["note_id"]] = nv
    ranked = sorted(merged.values(), key=lambda x: -x["score"])[:top_k]
    return ranked


def _bm25_search(query: str, kind: str | None = None, top_k: int = 10) -> list[dict[str, Any]]:
    """BM25 全文检索（jieba 分词后 FTS5），支持 kind 过滤。"""
    q = segment(query)
    if not q:
        return []
    conn = _connect()
    try:
        sql = "SELECT note_id, title, tags, model, kind, updated_at, bm25(notes) AS score FROM notes WHERE notes MATCH ?"
        params: list[Any] = [q]
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        sql += " ORDER BY score LIMIT ?"
        params.append(top_k)
        rows = conn.execute(sql, params).fetchall()
        return [
            {
                "note_id": r[0],
                "title": r[1],
                "tags": (r[2] or "").split(),
                "model": r[3],
                "kind": r[4],
                "updated_at": r[5],
                "score": round(r[6], 4),
                "method": "bm25",
            }
            for r in rows
        ]
    except sqlite3.OperationalError:
        # FTS 语法错误等：降级为空结果，不崩服务器
        return []
    finally:
        conn.close()


# ---------- 向量检索（TF-IDF + 余弦，纯本地） ----------
_vec_cache: list[dict[str, Any]] | None = None
_vec_cache_key: str | None = None


def _corpus() -> list[dict[str, Any]]:
    """懒加载全库文档（note_id, tokens, kind），按索引文件 mtime 缓存。"""
    global _vec_cache, _vec_cache_key  # noqa: PLW0603
    key = f"{INDEX_PATH.stat().st_mtime_ns}:{INDEX_PATH.stat().st_size}" if INDEX_PATH.exists() else "empty"
    if _vec_cache is not None and _vec_cache_key == key:
        return _vec_cache
    conn = _connect()
    try:
        rows = conn.execute("SELECT note_id, content, kind FROM notes").fetchall()
    finally:
        conn.close()
    docs = [{"note_id": r[0], "tokens": r[1].split(), "kind": r[2]} for r in rows]
    _vec_cache, _vec_cache_key = docs, key
    return docs


def _tfidf_search(query: str, kind: str | None = None, top_k: int = 10) -> list[dict[str, Any]]:
    """TF-IDF + 余弦相似度：查询词子空间投影，短查询下高效且可审计。"""
    docs = _corpus()
    qt = Counter(segment(query).split())
    if not qt or not docs:
        return []
    N = len(docs)
    df: Counter = Counter()
    for d in docs:
        df.update(set(d["tokens"]))
    idf = {t: math.log((1 + N) / (1 + df[t])) + 1.0 for t in qt}
    scored: list[dict[str, Any]] = []
    for d in docs:
        if kind and d["kind"] != kind:
            continue
        doc_tf = Counter(d["tokens"])
        num = 0.0
        dnorm = 0.0
        qnorm = 0.0
        for t, qtf in qt.items():
            wq = qtf * idf[t]
            wd = doc_tf.get(t, 0) * idf[t]
            num += wq * wd
            qnorm += wq * wq
            dnorm += wd * wd
        if qnorm == 0.0 or dnorm == 0.0:
            continue
        cos = num / (math.sqrt(qnorm) * math.sqrt(dnorm))
        if cos > 0.0:
            scored.append({"note_id": d["note_id"], "kind": d["kind"], "score": round(cos, 4), "method": "vector"})
    scored.sort(key=lambda x: -x["score"])
    return scored[:top_k]


def rebuild_index() -> dict[str, Any]:
    """从 markdown 全量重建索引。"""
    INDEX_PATH.unlink(missing_ok=True)
    _reset_vec_cache()
    n = 0
    for rel, _ in _walk_vault():
        try:
            note = read_note(rel)
            _index(rel, note["meta"], note["content"])
            n += 1
        except Exception:  # noqa: BLE001 —— 单文件损坏不阻塞重建
            continue
    return {"indexed": n}


def _reset_vec_cache() -> None:
    global _vec_cache, _vec_cache_key  # noqa: PLW0603
    _vec_cache = None
    _vec_cache_key = None


def _walk_vault():
    for sub in VAULT_DIRS.values():
        for p in sorted((VAULT_PATH / sub).glob("*.md")):
            yield p.relative_to(VAULT_PATH).as_posix(), p
