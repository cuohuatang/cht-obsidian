# cut-bicuo-zjflow-mcp

一体化 MCP 服务器：**自动记忆 + 自动总结 + 踩坑本(errlore式) + 纠错台账(AgentRecall式) + Obsidian 嫁接(obsidian-mcp式) + 会话交接(session-handoff式) + 技能沉淀(session-to-skill式)**。
免费、免 API key、纯本地，一套工具接入 Claude Code / Cursor / OpenClaw / Hermes / Codex 等所有 MCP 客户端。

> 当前状态：**V0.2 已发布**（GitHub 公开仓库 `cuohuatang/cut-bicuo-zjflow-mcp`，tag v0.2.0）。完整设计见 [DESIGN.md](DESIGN.md)。
> V0.2 核心：**静默提炼工作方式/工作流并提示生成 skill**——`cm_skill_propose` 从历史记录真实提炼步骤、规则、失败处理与来源双链，生成可安装 SKILL.md 草稿。

## 快速开始

```bash
pip install -e ".[dev]"
cut-bicuo-zjflow-mcp --help        # CLI 入口
python -m pytest -q          # 跑测试（13 项全过）
```

以 MCP 服务器方式运行：

```bash
# 方式一：源码直接跑
mcp run src/cut_bicuo_zjflow_mcp/server.py

# 方式二（发版后）：从 PyPI 拉取
uvx cut-bicuo-zjflow-mcp
```

## 接入（所有 Agent 同一份 JSON）

```json
{
  "mcpServers": {
    "cut-bicuo-zjflow": {
      "command": "uvx",
      "args": ["cut-bicuo-zjflow-mcp"],
      "env": { "CUT_BICUO_ZJFLOW_VAULT_PATH": "D:/Obsidian/你的库/vault" }
    }
  }
}
```

Claude Code：`claude mcp add cut-bicuo-zjflow -- uvx cut-bicuo-zjflow-mcp`，或写入 `.mcp.json`。

环境变量均可编辑：`CUT_BICUO_ZJFLOW_HOME`（默认 `~/.cut-bicuo-zjflow`）、`CUT_BICUO_ZJFLOW_VAULT_PATH`、`CUT_BICUO_ZJFLOW_INDEX_PATH`。

## 工具一览（18 个）

| 模块 | 工具 |
|---|---|
| 记忆 | `cm_memory_save` `cm_memory_recall` `cm_memory_search` |
| 总结 | `cm_summarize` `cm_summary_weekly` |
| 踩坑本 | `cm_lesson_add` `cm_lesson_inject` |
| 纠错台账 | `cm_correction_log` `cm_correction_verify` `cm_correction_check` |
| Obsidian | `cm_vault_init` `cm_obsidian_read` `cm_obsidian_write` |
| 会话交接 | `cm_handoff_create` `cm_handoff_list` `cm_handoff_resume` |
| 技能沉淀 | `cm_skill_suggest` `cm_skill_propose` |

## V0.2 核心：静默提炼工作流 → 生成 skill

```
每次会话结束：cm_summarize 沉淀要点 → cm_skill_suggest 检查重复工作流
→ 同一主题≥2次即自动提示："需要我把『×××』静默提炼成一个 skill 吗？"
→ 用户同意后 cm_skill_propose 从历史记录真实提炼：
   工作流步骤（编号列表/命令/动词句）+ 规则（踩坑本）+ 失败处理（纠错台账）+ 来源双链
   → 生成 SKILL.md 草稿（只展示不写盘，推荐 ~/.agents/skills/<name>/SKILL.md）
```

## 检索（混合）

默认 **hybrid = BM25（SQLite FTS5）+ TF-IDF 向量余弦**（纯本地、无外部模型），结果带 `method: bm25/hybrid/vector` 字段可审计；中文经 jieba 分词。

## 数据（Obsidian 唯一真相源）

```
~/.cut-bicuo-zjflow/vault/           ← markdown 真相源（Obsidian 直接打开）
├── 01-流水账/YYYY-MM-DD.md    ← 记忆
├── 02-踩坑本/<slug>.md        ← 踩坑本（errlore 式，含 [[双链]] 回源）
├── 03-纠错台账/<slug>.md      ← 纠错台账（AgentRecall 式，含 [[双链]] 回源）
├── 04-经验总结/<slug>.md      ← 自动总结
└── 05-交接/<date>-<slug>.md   ← 六段式会话交接（V0.2）
~/.cut-bicuo-zjflow/index.sqlite     ← 检索索引（FTS5 + 向量缓存，可重建）
```

双链约定：`cm_lesson_add(..., links=["01-流水账/2026-10-09"])`、`cm_correction_log(..., links=[...])` → 写入 frontmatter 并在正文渲染 `[[...]]`，Obsidian 图谱互通。

## 许可

MIT © cuohuatang
