"""cut-obsidian-mcp 服务器入口：MCPServer 注册全部 34 个 cm_ 工具（V0.6）。

V0.6 = Harness² 嫁接：cm_harness2_* 7 工具（递归优化 Agent 外壳：提示词/护栏/记忆/工具指导）
+ cm_doctor 自体检 + harness2://usage 资源；经验闭环沉淀回第二大脑。
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from . import __version__
from .modules import brain, corrections, github_sync, handoff, harness, lessons, memory, obsidian, skillcraft, summarize
from .modules.harness import STANDING_ORDERS

mcp = MCPServer(
    name="cut-obsidian-mcp",
    instructions=(
        "一体化第二大脑：自动记忆、自动总结、踩坑本(errlore式)、纠错台账(AgentRecall式)、"
        "Obsidian 嫁接、会话交接(session-handoff式)、技能沉淀(session-to-skill式)、"
        "后台消化(GitHub 私有仓库实时同步 + MOC 双链导航)、Harness² 外壳优化(递归优化提示词/护栏/记忆/工具指导)。全部本地存储、免 API key；"
        "混合检索（BM25 + TF-IDF 向量）。\n"
        "接入任意 Agent（Claude Code/Cursor/Codex/OpenCode/Gemini CLI/豆包工作台等）后：\n"
        "1) 开工前：cm_memory_recall + cm_correction_check + cm_lesson_inject（带上 agent 参数）；\n"
        "2) 工作中：cm_memory_save / cm_lesson_add / cm_correction_log（填 agent 与 category 分类项目）；\n"
        "3) 会话结束：cm_brain_finalize —— 自动周总结 + 技能建议 + 消化管线 + GitHub 实时上传；\n"
        "4) 首次使用先 cm_vault_init，云端镜像先 cm_github_setup(repo, token, branch)；\n"
        "5) 环境存疑先 cm_doctor 一键自体检。\n\n"
        + STANDING_ORDERS
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


# ---------- ⑩ 自体检 + Harness² 嫁接（V0.6）----------
@mcp.tool()
def cm_doctor() -> dict[str, Any]:
    """cht-obsidian 一键自体检：vault 可写/config 权限/git/索引/GitHub 同步/Harness² CLI，返回分级报告与修复建议。"""
    return harness.self_doctor()


@mcp.tool()
def cm_harness2_doctor(workdir: str | None = None) -> str:
    """Harness² 环境体检：CLI 是否在 PATH、Python≥3.12、uv、.env。跑任何基准前先调用。

    【常驻指令】每个工作会话开始、以及每次优化循环之前，先调用本工具；
    CLI 缺失时按返回的安装指引处理，停止重试不要空转。
    """
    return harness.doctor(workdir)


@mcp.tool()
def cm_harness2_demo(output: str = "runs/demo", k: int = 2, mode: str = "both", timeout: int = 900, workdir: str | None = None) -> str:
    """运行 Harness² 本地演示（确定性编辑器 + 真实 Python 执行，无需任何模型密钥）。"""
    return harness.demo(output, k, mode, timeout, workdir)


@mcp.tool()
def cm_harness2_setup(benchmark: str, substrate: str = "oc", dry_run: bool = False, timeout: int = 900, workdir: str | None = None) -> str:
    """安装某个基准的数据与环境。benchmark: jb(JobBench) | lab(LAB) | wb(WorkBuddy-Bench)。"""
    return harness.setup(benchmark, substrate, dry_run, timeout, workdir)


@mcp.tool()
def cm_harness2_check(bench: str, subset: str | None = None, substrate: str = "oc", timeout: int = 900, workdir: str | None = None) -> str:
    """跑基准前的环境检查（judge 是否就绪、任务是否可加载）。bench: jb | lab | wb。"""
    return harness.check(bench, subset, substrate, timeout, workdir)


@mcp.tool()
def cm_harness2_run(
    bench: str,
    k: int = 1,
    mode: str = "parallel",
    substrate: str = "oc",
    subset: str | None = None,
    only_domains: str = "",
    max_tasks: int | None = None,
    split: str = "all",
    workers: int = 1,
    seed: int | None = None,
    dry_run: bool = False,
    timeout: int = 900,
    workdir: str | None = None,
) -> str:
    """执行一次递归优化 sweep（核心入口，会调用模型、产生费用）。

    【常驻指令】标准动作永远是两步：先 dry_run=true 预览任务流（零成本），
    确认无误后以 max_tasks=1 小跑，拿到结果再依次调用 cm_harness2_judge 和
    cm_harness2_report。严禁一步到位全量跑；judge/report 参数必须与本次完全一致。
    """
    return harness.run(bench, k, mode, substrate, subset, only_domains, max_tasks, split, workers, seed, dry_run, timeout, workdir)


@mcp.tool()
def cm_harness2_judge(bench: str, k: int = 1, mode: str = "parallel", substrate: str = "oc", subset: str | None = None, seed: int | None = None, timeout: int = 900, workdir: str | None = None) -> str:
    """对已完成的 sweep 评分（judging）。参数必须与 cm_harness2_run 完全一致。

    【常驻指令】每次 cm_harness2_run 成功结束后必须接着调用本工具，再用
    cm_harness2_report 汇总——只有 judge+report 完成，本轮经验才会写入改进库。
    跳过评分 = 白跑。
    """
    return harness.judge(bench, k, mode, substrate, subset, seed, timeout, workdir)


@mcp.tool()
def cm_harness2_report(bench: str, k: str = "1", mode: str = "parallel", substrate: str = "oc", subset: str | None = None, timeout: int = 900, workdir: str | None = None) -> str:
    """汇总评分结果并生成报告。k 接受逗号列表，如 "1,2,3"（对应多次 sweep）。

    【常驻指令】本工具是优化循环的最后一步：judge 完成后必须调用，只有 report
    产出，本轮经验与结果才落盘归档；随后把被采纳的外壳改动用 cm_memory_save /
    cm_lesson_add 沉淀回第二大脑（闭环）。
    """
    return harness.report(bench, k, mode, substrate, subset, timeout, workdir)


@mcp.resource("harness2://usage")
def harness2_usage() -> str:
    """Harness² 完整使用手册（安装 / demo / 基准 / 参数 / 成本与安全注意事项）。"""
    return harness.usage_text()


def main() -> None:
    """CLI 入口：mcp.run() 走 stdio。"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
