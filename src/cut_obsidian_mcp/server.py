"""cut-obsidian-mcp 服务器入口：MCPServer 注册全部 26 个 cm_ 工具（V0.3）。

V0.3 = 第二大脑：多 Agent 分空间 + 后台自动消化管线（提炼→工作流→标签→双链→MOC）
+ GitHub 私有仓库实时同步（Obsidian 开机经 obsidian-git 自动拉取）。
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from . import __version__
from .modules import brain, corrections, github_sync, handoff, lessons, memory, obsidian, skillcraft, summarize

mcp = MCPServer(
    name="cut-obsidian-mcp",
    instructions=(
        "一体化第二大脑：自动记忆、自动总结、踩坑本(errlore式)、纠错台账(AgentRecall式)、"
        "Obsidian 嫁接、会话交接(session-handoff式)、技能沉淀(session-to-skill式)、"
        "后台消化(GitHub 私有仓库实时同步 + MOC 双链导航)。全部本地存储、免 API key；"
        "混合检索（BM25 + TF-IDF 向量）。\n"
        "接入任意 Agent（Claude Code/Cursor/Codex/OpenCode/Gemini CLI/豆包工作台等）后：\n"
        "1) 开工前：cm_memory_recall + cm_correction_check + cm_lesson_inject（带上 agent 参数）；\n"
        "2) 工作中：cm_memory_save / cm_lesson_add / cm_correction_log（填 agent 与 category 分类项目）；\n"
        "3) 会话结束：cm_brain_finalize —— 自动周总结 + 技能建议 + 消化管线 + GitHub 实时上传；\n"
        "4) 首次使用先 cm_vault_init，云端镜像先 cm_github_setup(repo, token, branch)。"
    ),
)


# ---------- ① 记忆 ----------
@mcp.tool()
def cm_memory_save(content: str, title: str | None = None, tags: list[str] | None = None, agent: str | None = None, category: str | None = None) -> dict[str, Any]:
    """记录一次会话事实/上下文到流水账（自动记忆；agent/category 供第二大脑分空间聚类）。"""
    return memory.save(content, title, tags, agent, category)


@mcp.tool()
def cm_memory_recall(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """开工前召回相关历史记忆。"""
    return memory.recall(query, top_k)


@mcp.tool()
def cm_memory_search(query: str, top_k: int = 10) -> list[dict[str, Any]]:
    """全库搜索记忆。"""
    return memory.search(query, top_k)


# ---------- ② 总结 ----------
@mcp.tool()
def cm_summarize(days: int = 1, output_dir: str = "04-经验总结") -> dict[str, Any]:
    """把最近 N 天流水整理为结构化经验。"""
    return summarize.summarize(days, output_dir)


@mcp.tool()
def cm_summary_weekly(scope: str = "week") -> dict[str, Any]:
    """每周自动总结：流水+踩坑+纠错 → 方法论。"""
    return summarize.weekly(scope)


# ---------- ③ 踩坑本（errlore 式）----------
@mcp.tool()
def cm_lesson_add(lesson: str, tags: list[str] | None = None, model: str | None = None, severity: str = "medium", links: list[str] | None = None, agent: str | None = None, category: str | None = None) -> dict[str, Any]:
    """文件式记录一条教训到踩坑本（专治二次犯错；links 为 Obsidian 双链回源）。"""
    return lessons.add(lesson, tags, model, severity, links, agent, category)


@mcp.tool()
def cm_lesson_inject(query: str, top_k: int = 3) -> dict[str, Any]:
    """开工前注入相关已知教训（含模型信任度标注）。"""
    return lessons.inject(query, top_k)


# ---------- ④ 纠错台账（AgentRecall 式）----------
@mcp.tool()
def cm_correction_log(correction: str, evidence: str | None = None, severity: str = "medium", model: str | None = None, links: list[str] | None = None, agent: str | None = None, category: str | None = None) -> dict[str, Any]:
    """记录一次用户纠正（严重度/证据），跨会话保留（links 为 Obsidian 双链回源）。"""
    return corrections.log(correction, evidence, severity, model, links, agent, category)


@mcp.tool()
def cm_correction_verify(note_id: str, took_effect: bool, note: str | None = None) -> dict[str, Any]:
    """标记纠正是否真正生效。"""
    return corrections.verify(note_id, took_effect, note)


@mcp.tool()
def cm_correction_check(query: str | None = None, top_k: int = 5) -> list[dict[str, Any]]:
    """开工前检查历史纠正+教训。"""
    return corrections.check(query, top_k)


# ---------- ⑤ Obsidian 桥梁 ----------
@mcp.tool()
def cm_vault_init(path: str | None = None) -> dict[str, Any]:
    """初始化 vault 目录与索引（幂等）。"""
    return obsidian.vault_init(path)


@mcp.tool()
def cm_obsidian_read(path: str) -> dict[str, Any]:
    """读取 vault 内 markdown（含 frontmatter）。"""
    return obsidian.read(path)


@mcp.tool()
def cm_obsidian_write(path: str, content: str, overwrite: bool = False) -> dict[str, Any]:
    """写入 vault 内 markdown（默认不覆盖）。"""
    return obsidian.write(path, content, overwrite)


# ---------- ⑥ 会话交接（session-handoff 式）----------
@mcp.tool()
def cm_handoff_create(
    task_overview: str,
    current_state: str,
    important_discoveries: str = "",
    next_steps: str = "",
    context_to_preserve: str = "",
    unanswered_question: str | None = None,
    from_agent: str | None = None,
    to_agent: str | None = None,
) -> dict[str, Any]:
    """把"上一个 Agent 干到哪"总结为六段式交接文档（跨 Agent 续命）。"""
    return handoff.create(
        task_overview, current_state, important_discoveries,
        next_steps, context_to_preserve, unanswered_question,
        from_agent, to_agent,
    )


@mcp.tool()
def cm_handoff_list(top_k: int = 10) -> list[dict[str, Any]]:
    """列出最近交接文档。"""
    return handoff.list_handoffs(top_k)


@mcp.tool()
def cm_handoff_resume(handoff_id: str) -> dict[str, Any]:
    """新 Agent 接手：读取交接；有未答问题先转问，否则直接开干。"""
    return handoff.resume(handoff_id)


# ---------- ⑦ 技能沉淀（session-to-skill / ritual 式，V0.2 核心）----------
@mcp.tool()
def cm_skill_suggest(top_k: int = 30) -> dict[str, Any]:
    """静默挖掘重复工作流，自动提示"需要我把×××生成一个 skill 吗？"。"""
    return skillcraft.suggest(top_k)


@mcp.tool()
def cm_skill_propose(target: str, tags: list[str] | None = None) -> dict[str, Any]:
    """从历史记录静默提炼工作流，生成 SKILL.md 草稿（只展示，确认后才写盘）。"""
    return skillcraft.propose(target, tags)


# ---------- ⑧ 第二大脑：GitHub 私有仓库同步（V0.3 核心）----------
@mcp.tool()
def cm_github_setup(repo: str, token: str, branch: str = "main") -> dict[str, Any]:
    """配置 GitHub 私有仓库作为云端镜像（token 只存本地 0600 文件，绝不外泄）。"""
    return github_sync.setup(repo, token, branch)


@mcp.tool()
def cm_github_push(message: str = "") -> dict[str, Any]:
    """把 vault 全部增量实时 push 到 GitHub 私有仓库。"""
    return github_sync.push(message)


@mcp.tool()
def cm_github_pull() -> dict[str, Any]:
    """从 GitHub 私有仓库拉取合并到本地 vault。"""
    return github_sync.pull()


@mcp.tool()
def cm_github_status() -> dict[str, Any]:
    """本地与远端差异概览（待推送/待拉取数量，不含 token）。"""
    return github_sync.status()


# ---------- ⑨ 第二大脑：后台自动消化管线（V0.3 核心）----------
@mcp.tool()
def cm_brain_process(agent: str | None = None, project: str | None = None, since_days: int = 7) -> dict[str, Any]:
    """一键消化：收集该 Agent 的分类项目素材→聚类→提炼→工作流页→打标签→双链→MOC。"""
    return brain.process(agent, project, since_days)


@mcp.tool()
def cm_brain_finalize(agent: str | None = None, push: bool = True) -> dict[str, Any]:
    """会话终结钩子：周总结 + 技能建议 + 消化管线 + GitHub 实时上传（一条命令收尾）。"""
    return brain.finalize(agent, push)


@mcp.tool()
def cm_brain_moc(agent: str | None = None) -> dict[str, Any]:
    """生成/更新第二大脑 MOC 导航页（按分类聚合全部工作流双链）。"""
    moc_rel = brain._moc(agent)  # noqa: SLF001 —— 内部函数直接复用
    return {"moc": moc_rel}


@mcp.tool()
def cm_brain_status() -> dict[str, Any]:
    """第二大脑统计：笔记数、工作流数、待消化数、GitHub 同步状态。"""
    return brain.status()


def main() -> None:
    """CLI 入口：mcp.run() 走 stdio。"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
