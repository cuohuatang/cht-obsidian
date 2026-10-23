# cut-bicuo-zjflow-mcp

一体化 **第二大脑** MCP 服务器：**自动记忆 + 自动总结 + 踩坑本(errlore式) + 纠错台账(AgentRecall式) + Obsidian 嫁接(obsidian-mcp式) + 会话交接(session-handoff式) + 技能沉淀(session-to-skill式) + GitHub 私有仓库实时同步**。
免费、免 API key、纯本地，一套工具接入所有支持 MCP 的 Agent（Claude Code / Cursor / Codex / OpenCode / Gemini CLI / 豆包工作台等）。

> 当前状态：**V0.3 已开发完成**（26 工具，GitHub 仓库 `cuohuatang/cut-bicuo-zjflow-mcp`，tag v0.3.0）。
> V0.3 核心 = **第二大脑 + 云端镜像**：智能体工作时后台自动消化其各分类项目 → 提炼/总结/萃取成工作流 → 打标签 → 双链 → 实时上传 GitHub 私有仓库 → 本地 Obsidian 开机经 obsidian-git 自动拉取。完整设计见 [DESIGN.md](DESIGN.md)，版本记录见 [CHANGELOG.md](CHANGELOG.md)。

## 快速开始

```bash
pip install -e ".[dev]"
cut-bicuo-zjflow-mcp        # 以 MCP 服务器运行（stdio）
python -m pytest -q         # 跑测试（22 项全过）
```

## 接入（所有 Agent 同一份 JSON）

```json
{
  "mcpServers": {
    "cut-bicuo-zjflow": {
      "command": "uvx",
      "args": ["cut-bicuo-zjflow-mcp"],
      "env": {
        "CUT_BICUO_ZJFLOW_VAULT_PATH": "D:/Obsidian/你的库/vault",
        "CUT_BICUO_ZJFLOW_GITHUB_REPO": "你的账号/cut-bicuo-brain",
        "CUT_BICUO_ZJFLOW_GITHUB_TOKEN": "你的私有仓库 token"
      }
    }
  }
}
```

Claude Code：`claude mcp add cut-bicuo-zjflow -- uvx cut-bicuo-zjflow-mcp`，或写入 `.mcp.json`。

环境变量均可编辑：`CUT_BICUO_ZJFLOW_HOME`、`CUT_BICUO_ZJFLOW_VAULT_PATH`、`CUT_BICUO_ZJFLOW_INDEX_PATH`、`CUT_BICUO_ZJFLOW_GITHUB_REPO/TOKEN/BRANCH`。token 也可经 `cm_github_setup` 写入本地 0600 文件，不强制放环境变量。

## 工具一览（26 个）

| 模块 | 工具 |
|---|---|
| 记忆 | `cm_memory_save` `cm_memory_recall` `cm_memory_search` |
| 总结 | `cm_summarize` `cm_summary_weekly` |
| 踩坑本 | `cm_lesson_add` `cm_lesson_inject` |
| 纠错台账 | `cm_correction_log` `cm_correction_verify` `cm_correction_check` |
| Obsidian | `cm_vault_init` `cm_obsidian_read` `cm_obsidian_write` |
| 会话交接 | `cm_handoff_create` `cm_handoff_list` `cm_handoff_resume` |
| 技能沉淀 | `cm_skill_suggest` `cm_skill_propose` |
| **GitHub 同步（V0.3）** | `cm_github_setup` `cm_github_push` `cm_github_pull` `cm_github_status` |
| **第二大脑（V0.3）** | `cm_brain_process` `cm_brain_finalize` `cm_brain_moc` `cm_brain_status` |

## V0.3 核心玩法：第二大脑 + GitHub 私有仓库实时同步

```
① 开工前   cm_memory_recall + cm_correction_check + cm_lesson_inject（agent=你的智能体）
② 工作中   cm_memory_save / cm_lesson_add / cm_correction_log（带 agent + category 分类项目）
③ 会话结束 cm_brain_finalize(agent=..., push=true) —— 一条命令：
           周总结 → 技能建议 → 消化管线（聚类→提炼→工作流页→打标签→双链→MOC）
           → 实时 push 到 GitHub 私有仓库
④ 云端镜像 任意 Agent 的笔记实时上传私有仓库；
           本地 Obsidian 装 obsidian-git 插件 → 开机自动 pull → 双链图谱即见
```

- **多 Agent 分空间**：每个智能体用自己的 `agent` 标识记录，第二大脑按 Agent 隔离记忆、按 `category` 聚合分类项目；
- **后台自动消化**：`cm_brain_process` 把窗口内未消化素材按共同标签聚类，自动提炼工作流步骤/规则/失败处理，生成 04-经验总结 主题页（frontmatter 含 type/category/status/confidence/knowledge_expire_date=+180天/last_updated/source/tags），原素材打"已消化"标签并双链回源；
- **MOC 导航**：06-第二大脑/<agent>/MOC.md 按分类自动聚合全部工作流页，Obsidian 图谱即第二大脑；
- **安全**：GitHub token 只存本地 0600 文件/环境变量，所有 git 输出脱敏，绝不外泄。

## V0.2 核心：静默提炼工作流 → 生成 skill

```
每次会话结束：cm_summarize 沉淀要点 → cm_skill_suggest 检查重复工作流
→ 同一主题≥2次即自动提示："需要我把『×××』静默提炼成一个 skill 吗？"
→ 用户同意后 cm_skill_propose 从历史记录真实提炼：
   工作流步骤 + 规则（踩坑本）+ 失败处理（纠错台账）+ 来源双链
   → 生成 SKILL.md 草稿（只展示不写盘，推荐 ~/.agents/skills/<name>/SKILL.md）
```

## 检索（混合）

默认 **hybrid = BM25（SQLite FTS5）+ TF-IDF 向量余弦**（纯本地、无外部模型），结果带 `method: bm25/hybrid/vector` 字段可审计；中文经 jieba 分词。

## 数据（Obsidian 唯一真相源）

```
~/.cut-bicuo-zjflow/vault/           ← markdown 真相源（Obsidian 直接打开）
├── 01-流水账/          ← 记忆（按 agent/category 打标）
├── 02-踩坑本/          ← 踩坑本（errlore 式，含 [[双链]] 回源）
├── 03-纠错台账/        ← 纠错台账（AgentRecall 式，含 [[双链]] 回源）
├── 04-经验总结/        ← 工作流主题页（消化管线自动生成）
├── 05-交接/            ← 六段式会话交接
└── 06-第二大脑/<agent>/MOC.md   ← MOC 导航（V0.3 自动聚合）
~/.cut-bicuo-zjflow/index.sqlite   ← 检索索引（FTS5 + 向量缓存，可重建）
```

双链约定：`cm_lesson_add(..., links=["01-流水账/2026-10-09"])`、`cm_correction_log(..., links=[...])` → 写入 frontmatter 并在正文渲染 `[[...]]`；消化管线自动给工作流页生成 `[[相对路径|标题]]` 双链，Obsidian 图谱互通。

## 许可

MIT © cuohuatang
