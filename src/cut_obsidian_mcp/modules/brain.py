"""⑨ 第二大脑模块（V0.3 核心：后台自动消化管线）。

智能体工作时，它把该 Agent 各分类项目的零散记录自动"消化"：
  收集候选素材 → 按主题/标签聚类 → 提炼要点与步骤 → 生成/更新经验工作流页
  → 打"已消化"标签 → 双链回源 → 更新 MOC 导航（第二大脑索引）
再经 cm_brain_finalize 一键串联：总结 + 技能建议 + 消化 + GitHub 实时上传。

全部为纯规则、可审计、可复算；双链使用 Obsidian 标准 [[相对路径|显示名]]。
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .. import config
from ..storage import vault
from . import github_sync, skillcraft

_KIND_TAGS = "已消化"
_DISTILL_KINDS = ("memory", "lessons", "corrections")
_SOURCE_DIRS = ("01-流水账", "02-踩坑本", "03-纠错台账")
_GENERIC_TAGS = {"已消化", "general", "通用"}


def _expire_date(days: int = 180) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _collect_candidates(since_days: int, agent: str | None) -> list[dict[str, Any]]:
    """收集窗口内未消化的素材（agent 为空=全部智能体）。"""
    since = (datetime.now() - timedelta(days=since_days)).isoformat()
    candidates: list[dict[str, Any]] = []
    for rel, _ in vault._walk_vault():  # noqa: SLF001 —— 存储层复用
        if not any(rel.startswith(d) for d in _SOURCE_DIRS):
            continue
        try:
            note = vault.read_note(rel)
        except Exception:  # noqa: BLE001
            continue
        meta = note["meta"]
        if meta.get("updated", "") < since:
            continue
        if _KIND_TAGS in meta.get("tags", []):
            continue
        if agent and meta.get("agent") != agent:
            continue
        candidates.append({**note, "rel": rel})
    return candidates


def _cluster(candidates: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """按共同标签聚类（一条笔记多标签可合并多组）；无标签按标题关键词聚合。"""
    tag_groups: dict[str, set[int]] = defaultdict(set)  # tag -> note 索引集合
    for i, c in enumerate(candidates):
        for tag in c["meta"].get("tags", []):
            if tag not in _GENERIC_TAGS:
                tag_groups[tag].add(i)
    # 合并共享笔记的标签组（union-find）
    parent = list(range(len(candidates)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for idxs in tag_groups.values():
        idxs = list(idxs)
        for i in range(1, len(idxs)):
            union(idxs[0], idxs[i])
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for i, c in enumerate(candidates):
        groups[find(i)].append(c)
    clusters = [sorted(g, key=lambda x: x["meta"].get("updated", "")) for g in groups.values()]
    # 按主题标签命名；无标签组用标题关键词
    named: list[tuple[str, list[dict[str, Any]]]] = []
    for g in clusters:
        tags = sorted({t for c in g for t in c["meta"].get("tags", []) if t not in _GENERIC_TAGS})
        if tags:
            named.append((tags[0], g))
        else:
            first = g[0]["meta"].get("title", "") or g[0]["content"][:20]
            named.append((first[:24], g))
    return [g for _, g in sorted(named, key=lambda x: x[0])]


def _distill(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    """从一组素材提炼：要点 / 步骤 / 规则 / 失败处理。"""
    records = [{"content": c["content"], "meta": c["meta"], "kind": c["meta"].get("type")} for c in cluster]
    steps = skillcraft._extract_steps(records)  # noqa: SLF001 —— 复用提炼器
    rules = skillcraft._extract_from_kind(records, "memory", max_items=5)  # noqa: SLF001
    pitfalls = skillcraft._extract_from_kind(records, "lesson", max_items=5)  # noqa: SLF001
    corrections = skillcraft._extract_from_kind(records, "correction", max_items=5)  # noqa: SLF001
    bullets = []
    seen: set[str] = set()
    for c in cluster:
        s = c["content"].strip().splitlines()[0][:80] if c["content"].strip() else ""
        if s and s not in seen:
            seen.add(s)
            bullets.append(f"- {s}")
    return {
        "steps": steps,
        "rules": rules,
        "pitfalls": pitfalls,
        "corrections": corrections,
        "bullets": bullets[:6],
    }


def _obsidian_link(rel: str, title: str | None = None) -> str:
    title = title or Path(rel).stem
    return f"[[{rel}|{title}]]"


def _write_workflow(topic: str, cluster: list[dict[str, Any]], distilled: dict[str, Any], agent: str | None) -> str:
    """写/更新 04-经验总结 下的工作流主题页，返回相对路径。"""
    today = date.today().isoformat()
    wf_id = f"wf-{uuid.uuid4().hex[:10]}"
    slug = vault.slugify(topic, 40)
    agent_suffix = f"-{vault.slugify(agent, 20)}" if agent else ""
    rel = f"{config.VAULT_DIRS['summaries']}/{today}-{slug}{agent_suffix}.md"  # 同主题同日复用同页 → 不断优化
    sources = [_obsidian_link(c["rel"], c["meta"].get("title") or "") for c in cluster]
    source_paths = [c["rel"] for c in cluster]
    steps_block = "\n".join(f"{i+1}. {s}" for i, s in enumerate(distilled["steps"])) or "（记录不足，暂无明确步骤）"
    rules_block = "\n".join(f"- {r}" for r in distilled["rules"]) or "- 无"
    pitfalls_block = "\n".join(f"- {p}" for p in distilled["pitfalls"]) or "- 暂无踩坑记录"
    corr_block = "\n".join(f"- {c}" for c in distilled["corrections"]) or "- 暂无纠错记录"
    agents = sorted({c["meta"].get("agent", "default") for c in cluster})
    all_tags = sorted({t for c in cluster for t in c["meta"].get("tags", []) if t not in _GENERIC_TAGS})

    body = f"""# 工作流：{topic}

## 要点
{chr(10).join(distilled["bullets"]) or "- （素材较简略）"}

## 工作流步骤（自动提炼）
{steps_block}

## 规则
{rules_block}

## 失败处理（踩坑本）
{pitfalls_block}

## 纠错台账
{corr_block}

## 来源（双链回源）
{chr(10).join(f"- {s}" for s in sources)}
"""
    meta: dict[str, Any] = {
        "note_id": wf_id,
        "title": f"工作流：{topic}",
        "type": "workflow",
        "category": topic,
        "agent": (agent or "default"),
        "agents": agents,
        "status": "verified" if len(cluster) >= 2 else "draft",
        "confidence": 0.8 if len(cluster) >= 2 else 0.6,
        "knowledge_expire_date": _expire_date(180),
        "source": source_paths,
        "tags": all_tags,
    }
    vault.write_note(rel, body, meta, overwrite=True)
    return rel


def _mark_processed(c: dict[str, Any], wf_rel: str) -> None:
    """给原始素材打"已消化"标签并追加双链（只改 frontmatter+末尾引用，不改原文）。"""
    meta = dict(c["meta"])
    tags = list(meta.get("tags", []))
    if _KIND_TAGS not in tags:
        tags.append(_KIND_TAGS)
    meta["tags"] = tags
    body = c["content"].strip()
    if "双链" not in body and wf_rel not in body:
        body = f"{body}\n\n> 已消化为工作流：{_obsidian_link(wf_rel)}"
    vault.write_note(c["rel"], body, meta, overwrite=True)


def _moc(agent: str | None, moc_rel: str | None = None) -> str:
    """生成 MOC（第二大脑导航）：按分类聚合所有工作流页，双链索引。"""
    wf_pages: list[tuple[str, dict[str, Any]]] = []
    for rel, _ in vault._walk_vault():  # noqa: SLF001
        if not rel.startswith(config.VAULT_DIRS["summaries"]):
            continue
        try:
            note = vault.read_note(rel)
        except Exception:  # noqa: BLE001
            continue
        if note["meta"].get("type") == "workflow":
            if agent and note["meta"].get("agent") != agent and "default" not in note["meta"].get("agents", []):
                continue
            wf_pages.append((rel, note["meta"]))
    wf_pages.sort(key=lambda x: x[1].get("category", ""))
    by_cat: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for rel, meta in wf_pages:
        by_cat[meta.get("category", "未分类")].append((rel, meta))
    lines = []
    for cat in sorted(by_cat):
        lines.append(f"## {cat}")
        for rel, meta in by_cat[cat]:
            status = meta.get("status", "draft")
            lines.append(f"- {_obsidian_link(rel, meta.get('title', ''))} · {status}")
    title = f"第二大脑 MOC（{agent or '全部 Agent'}）"
    moc_rel = moc_rel or f"{config.VAULT_DIRS['brain']}/{agent or '00-全部'}/MOC.md"
    body = f"""# {title}

> 自动生成：按分类聚合全部工作流页。Obsidian 中点击双链即可直达，全库互为第二大脑。

{chr(10).join(lines) if lines else "（暂无工作流页，先运行 cm_brain_process 消化素材）"}
"""
    meta = {
        "note_id": f"moc-{uuid.uuid4().hex[:8]}",
        "title": title,
        "type": "moc",
        "category": "导航",
        "agent": agent or "all",
        "status": "auto",
        "confidence": 1.0,
        "knowledge_expire_date": _expire_date(30),
        "tags": ["moc", "导航"],
    }
    vault.write_note(moc_rel, body, meta, overwrite=True)
    return moc_rel


def process(agent: str | None = None, project: str | None = None, since_days: int = 7) -> dict[str, Any]:
    """一键消化管线：收集→聚类→提炼→工作流页→打标签→MOC。"""
    candidates = _collect_candidates(since_days, agent)
    if project:
        candidates = [c for c in candidates if project in c["meta"].get("category", "") or project in c["meta"].get("tags", [])]
    if not candidates:
        return {"processed": 0, "clusters": 0, "candidates": 0, "workflow_pages": [], "note": "窗口内无待消化素材"}
    clusters = _cluster(candidates)
    workflow_pages: list[str] = []
    for cluster in clusters:
        topic = _topic_of(cluster)
        distilled = _distill(cluster)
        wf_rel = _write_workflow(topic, cluster, distilled, agent)
        workflow_pages.append(wf_rel)
        for c in cluster:
            _mark_processed(c, wf_rel)
    moc_rel = _moc(agent)
    return {
        "processed": len(candidates),
        "clusters": len(clusters),
        "candidates": len(candidates),
        "workflow_pages": workflow_pages,
        "moc": moc_rel,
    }


def _topic_of(cluster: list[dict[str, Any]]) -> str:
    """确定工作流主题：优先共同标签，其次共同标题词，最后首条内容。"""
    tags = {t for c in cluster for t in c["meta"].get("tags", []) if t not in _GENERIC_TAGS}
    if tags:
        return sorted(tags)[0]
    titles = [c["meta"].get("title", "") for c in cluster]
    if len(set(titles)) == 1 and titles[0]:
        return titles[0]
    first = cluster[0]["meta"].get("title", "") or cluster[0]["content"][:20]
    return first[:24] or "未命名主题"


def finalize(agent: str | None = None, push: bool = True) -> dict[str, Any]:
    """会话终结钩子（一键）：周总结 → 技能建议 → 消化管线 → GitHub 实时上传。"""
    result: dict[str, Any] = {}
    result["summary"] = _safe_call(summarize_weekly, agent=agent)
    result["skill_suggest"] = _safe_call(lambda: skillcraft.suggest())
    result["brain_process"] = process(agent=agent)
    if push:
        cred = config.load_credentials()
        if cred.get("repo"):
            result["github_push"] = _safe_call(lambda: github_sync.push(f"会话终结自动同步（{datetime.now().isoformat(timespec='minutes')}）"))
        else:
            result["github_push"] = {"pushed": False, "message": "未配置 GitHub 仓库，跳过上传（可 cm_github_setup 开启实时镜像）"}
    return result


def _safe_call(fn, **kw):
    try:
        return fn(**kw) if kw else fn()
    except Exception as exc:  # noqa: BLE001 —— finalize 不因单步失败中断
        return {"error": str(exc)[:200]}


def summarize_weekly(agent: str | None = None) -> dict[str, Any]:
    """周总结（复用 summarize 模块；agent 过滤窗口内流水）。"""
    from .summarize import weekly
    return weekly()


def status() -> dict[str, Any]:
    """第二大脑统计：各目录笔记数、工作流/待消化数、GitHub 同步状态。"""
    counts: dict[str, int] = {}
    workflows = 0
    todo = 0
    for rel, _ in vault._walk_vault():  # noqa: SLF001
        sub = rel.split("/", 1)[0]
        counts[sub] = counts.get(sub, 0) + 1
        try:
            meta = vault.read_note(rel)["meta"]
        except Exception:  # noqa: BLE001
            continue
        if meta.get("type") == "workflow":
            workflows += 1
        if any(rel.startswith(d) for d in _SOURCE_DIRS) and _KIND_TAGS not in meta.get("tags", []):
            todo += 1
    gh = {}
    try:
        gh = github_sync.status()
    except Exception:  # noqa: BLE001
        gh = {"error": "git 不可用或未初始化"}
    return {
        "notes_by_dir": counts,
        "workflow_pages": workflows,
        "pending_digest": todo,
        "vault_path": str(config.VAULT_PATH),
        "github": gh,
    }
