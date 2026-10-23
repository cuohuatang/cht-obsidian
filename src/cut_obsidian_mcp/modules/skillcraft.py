"""⑦ 技能沉淀模块（源自 squidllee/session-to-skill 精华，即"ritual 式"）：

静默提炼工作方式/工作流 → 自动提示生成 skill。

V0.2 核心升级：`cm_skill_propose` 不再输出空模板，而是从 vault 历史记录
（记忆/踩坑/纠错/交接）中**真实提炼有序步骤、规则、失败处理与来源双链**，
生成可直接安装的 SKILL.md 草稿。

精华移植（不依赖 entire CLI，用 cut-obsidian 自身数据驱动）：
- 先识别可复用行为，用证据（记忆/踩坑/纠错/交接记录）而非机械转换
- 只沉淀可复用工作流与规则，不含一次性内容、密钥、隐私
- 草稿先展示、不直接写文件；写文件必须用户确认；推荐跨 Agent 路径 ~/.agents/skills/<name>/SKILL.md
- 自动提示机制：检测到同一主题重复出现时，主动问"需要我把×××生成一个 skill 吗？"
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from typing import Any

from ..storage import vault

_SUGGEST_MIN_REPEAT = 2  # 同一主题出现≥2次即判定为重复工作流

# 步骤行识别：编号列表 / 项目符号 / 命令行 / 含关键动词的短句
_STEP_VERBS = (
    "执行", "运行", "调用", "创建", "检查", "确认", "部署", "推送", "提交",
    "安装", "配置", "初始化", "启动", "停止", "重启", "下载", "上传", "生成",
    "编译", "测试", "验证", "发布", "登录", "认证", "克隆", "拉取", "合并",
    "切换", "修改", "删除", "备份", "恢复", "迁移", "转换", "导出", "导入",
    "分析", "计算", "查询", "更新", "升级", "降级", "清理", "优化", "监控",
    "告警", "接入", "注册", "扫描", "提炼", "总结", "记录", "注入",
)


def suggest(top_k: int = 30) -> dict[str, Any]:
    """扫描记忆/踩坑/纠错/交接，按 tags 聚类挖掘重复工作流，返回自动提示文案。"""
    hits = vault.recent(top_k=top_k)
    tag_counter: Counter = Counter()
    for h in hits:
        for tag in h.get("tags", []):
            tag_counter[tag] += 1
    repeats = sorted(
        ((tag, n) for tag, n in tag_counter.items() if n >= _SUGGEST_MIN_REPEAT),
        key=lambda x: -x[1],
    )
    suggestions = [
        {
            "workflow": tag,
            "occurrences": n,
            "evidence_kinds": sorted({h["kind"] for h in hits if tag in h.get("tags", [])}),
        }
        for tag, n in repeats[:5]
    ]
    if not suggestions:
        return {"suggestions": [], "prompt": "（暂无重复工作流，继续积累中）"}
    top = suggestions[0]
    prompt = (
        f"检测到重复工作流『{top['workflow']}』（出现 {top['occurrences']} 次），"
        f"需要我把『{top['workflow']}』静默提炼成一个 skill 吗？"
    )
    return {"suggestions": suggestions, "prompt": prompt}


def propose(target: str, tags: list[str] | None = None) -> dict[str, Any]:
    """把重复工作流沉淀为 SKILL.md 草稿（从历史记录真实提炼，只展示不写盘）。"""
    name = _to_kebab(target)
    skill_name = f"{name}-skill"
    description = f"Use when the user wants to {target}（重复工作流自动沉淀）。"

    # ① 召回相关历史记录：关键词搜索 + tags 关联（静默提炼不只靠关键词）
    hits = vault.search(target, top_k=10)
    seen_ids = {h["note_id"] for h in hits}
    if tags:
        for h in vault.recent(top_k=30):
            if h["note_id"] not in seen_ids and any(t in h.get("tags", []) for t in tags):
                hits.append(h)
                seen_ids.add(h["note_id"])
    records: list[dict[str, Any]] = []
    for h in hits:
        note = vault.read_note_by_id(h["note_id"])
        if note:
            records.append({**h, "content": note["content"], "meta": note["meta"]})

    # ② 从记录中提炼工作流步骤 / 规则 / 失败处理
    steps = _extract_steps(records)
    rules = _extract_from_kind(records, "lesson", max_items=5)
    pitfalls = _extract_from_kind(records, "correction", max_items=5)
    sources = [f"[[{r['note_id']}]]" for r in records[:5]]

    # ③ 组装 SKILL.md 草稿
    workflow_block = (
        "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))
        if steps
        else "（历史记录不足，未提炼到明确步骤；建议手动补充后再安装）"
    )
    rules_block = (
        "\n".join(f"- {r}" for r in rules)
        if rules
        else "- 开工前先 cm_memory_recall + cm_correction_check 召回历史与踩坑。"
    )
    pitfalls_block = (
        "\n".join(f"- {p}" for p in pitfalls)
        if pitfalls
        else "- 遇到未收录的新情况：cm_lesson_add 记录教训，向用户确认是否扩展本技能。"
    )
    sources_block = "\n".join(f"- {s}" for s in sources) if sources else "- （暂无来源记录）"

    draft = f"""---
name: {skill_name}
description: {description}
tags: [{', '.join(tags or [])}]
source: cut-obsidian-mcp skillcraft（静默提炼）
---

# {skill_name}

## 目的
把重复工作流「{target}」固化为可复用技能，避免每次从头开始、重复踩坑。

## 规则
{rules_block}

## 工作流（从历史记录静默提炼）
{workflow_block}

## 验证
- 产物与成功标准逐项对照。
- 新教训 cm_lesson_add 写入踩坑本后，下次 cm_lesson_inject 自动注入。

## 失败处理
{pitfalls_block}

## 来源记录（双链回源）
{sources_block}
"""
    return {
        "skill_name": skill_name,
        "target": target,
        "source_tags": tags or [],
        "evidence_count": len(records),
        "extracted_steps": len(steps),
        "sk_md_draft": draft,
        "destination_recommended": f"~/.agents/skills/{skill_name}/SKILL.md",
        "note": "草稿仅展示，未写盘；确认后按你选择的路径安装（写盘前会再次征求同意）。",
    }


# ---------- 提炼辅助 ----------
def _looks_like_step(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 160:
        return False
    if re.match(r"^\d+[\.\、\)]", s):
        return True
    if re.match(r"^[-*•]", s):
        return True
    if s.startswith(("$", ">", "sudo ", "pip ", "npm ", "git ", "docker ", "uv ", "python ")):
        return True
    return any(v in s for v in _STEP_VERBS)


def _normalize_step(line: str) -> str:
    s = line.strip()
    s = re.sub(r"^\d+[\.\、\)]\s*", "", s)
    s = re.sub(r"^[-*•]\s*", "", s)
    return s.lstrip("$> ").strip()


def _extract_steps(records: list[dict[str, Any]], max_steps: int = 15) -> list[str]:
    steps: list[str] = []
    seen: set[str] = set()
    for rec in records:
        for line in rec.get("content", "").splitlines():
            if _looks_like_step(line):
                s = _normalize_step(line)
                if s and len(s) > 3 and s not in seen:
                    seen.add(s)
                    steps.append(s)
    return steps[:max_steps]


def _extract_from_kind(records: list[dict[str, Any]], kind: str, max_items: int = 5) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for rec in records:
        if rec.get("kind") != kind:
            continue
        for line in rec.get("content", "").splitlines():
            s = line.strip().lstrip("#>- ").strip()
            if s and len(s) > 4 and s not in seen and not s.startswith("（"):
                seen.add(s)
                items.append(s[:120])
                break
    return items[:max_items]


def _to_kebab(text: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text).strip("-")
    return (s[:40] or f"skill-{uuid.uuid4().hex[:6]}").lower()
