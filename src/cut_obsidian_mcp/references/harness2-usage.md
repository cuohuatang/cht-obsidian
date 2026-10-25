# Harness² 使用手册（cht-obsidian 内置版）

> 上游：https://github.com/google-research/harness2 （Apache-2.0）
> 主页：https://harness2.github.io ｜ 论文：arXiv:2610.14224
> 本文件随 cht-obsidian 分发，由 MCP 资源 `harness2://usage` 与 Skill 共同引用。
> 在 cht-obsidian 中，工具名为 `cm_harness2_*`（下文括号内标注）。

## 1. 它是什么

Harness² 是 Google Research 开源的**递归 Agent Harness 优化框架**：

- **Harness（外壳）**：环绕模型的系统层——系统提示词、护栏、记忆、工具指导、子智能体、Skills、脚本、插件，共 8 类可编辑组件。
- **Harnessing（优化）**：在不改模型权重（不微调、不 RL）的前提下，递归优化这层外壳。
- **两层递归**：
  1. 任务级：对新任务执行 **Propose–Probe–Compose**（提出修改方案 → 同任务实测对比 → 合并有效改动），**不需要标准答案**，靠行为对比获得证据；
  2. 外壳级：任务结束后把"被采纳的外壳 + 有证据的经验"写入长期改进库，指导下一次任务。
- 效果（官方）：单步在 WorkBuddy-Bench 最高 +11.5 分、JobBench +4.5 分、LAB 部分通过率 +11.8 个百分点。

**与 cht-obsidian 的关系**：第二大脑是"记忆库"（cm_memory_* / cm_lesson_* / cm_correction_*），
Harness² 是"优化器"（cm_harness2_*）。优化循环产出的经验用 cm_memory_save / cm_lesson_add
写回第二大脑，即形成"记忆库 × 优化器"闭环。

## 2. 安装（Linux + Python 3.12 + uv）

```bash
git clone https://github.com/google-research/harness2.git
cd harness2
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e '.[render]'
harness2-demo --output runs/demo --k 2   # 本地 demo：无需任何模型密钥
```

模型基准还需：Node.js 20+、Google Cloud CLI、`.env`、`gcloud auth application-default login`；
LAB 需 Pandoc + Poppler，WorkBuddy-Bench 需 Docker。

`.env` 配置项（`cp .env.example .env` 后编辑；shell 环境变量优先于 `.env`）：

| 变量 | 含义 |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | Vertex AI 项目 ID（必填） |
| `GOOGLE_CLOUD_LOCATION` | 区域，默认 `global` |
| `HARNESS2_SOLVER_MODEL` | 执行器模型（OpenCode 的 `provider/model` 格式，如 Vertex Gemini） |
| `HARNESS2_IMPROVER_MODEL` | 改进器模型，默认同执行器（支持 Vertex Claude/Gemini） |
| `HARNESS2_JUDGE_MODEL` | 裸裁判模型 ID（适配器自动加 Vertex 前缀） |
| `HARNESS2_RUNS_DIR` | 结果输出根目录，默认 `runs/` |

认证（任选一）：`gcloud auth application-default login`｜`GOOGLE_APPLICATION_CREDENTIALS`
指向服务账号 key 文件｜`gcloud auth application-default login --impersonate-service-account=<账号>`。
账户需有每个 configured 模型的访问权限；`gcloud` 需在 PATH 中（安装检查会跑
`gcloud auth application-default print-access-token`）。

**不想用 Google 的替代路线**：Codex executor（`--substrate cx`）可接任意 Responses API
端点——设 `HARNESS2_CODEX_BASE_URL` / `HARNESS2_CODEX_API_KEY` / `HARNESS2_CODEX_MODEL`
即可用自己的大模型服务；WorkBuddy-Bench 下 Codex 跑在 Docker 里，需 `harness2-bridge --host 0.0.0.0`。

**哪些功能零凭证**：`cm_harness2_demo`（确定性编辑器 + 真实 Python 执行，不调模型）、
`cm_harness2_doctor` / `cm_harness2_check` / `cm_harness2_setup --dry-run`（只检查不调用）、
以及 cht-obsidian 全部本地工具（`cm_memory_*` 等，jieba+FTS5+TF-IDF 纯本地）。

> 云端多用户版（154.12.41.33:8899）默认不安装 Harness² CLI：每位用户需自带模型凭证，
> 云端调用 cm_harness2_* 会得到安装指引。完整功能请在本地以 stdio 模式运行 cht-obsidian，
> 或用 `HARNESS2_CMD_<KEY>` 环境变量把 CLI 路径指给你自己的安装。

## 3. 工具一览（cht-obsidian 内）

| 工具（cm_harness2_*） | 对应 CLI | 说明 |
|---|---|---|
| `cm_harness2_doctor` | — | 环境体检：CLI 是否在 PATH、Python≥3.12、uv、.env |
| `cm_harness2_demo` | `harness2-demo` | 本地演示，无需模型密钥 |
| `cm_harness2_setup` | `harness2-setup` | 安装基准（jb/lab/wb） |
| `cm_harness2_check` | `harness2-check` | 跑前环境检查 |
| `cm_harness2_run` | `harness2` | 执行递归优化 sweep（核心，会计费；支持 dry_run） |
| `cm_harness2_judge` | `harness2-judge` | 评分（参数须与 sweep 一致） |
| `cm_harness2_report` | `harness2-report` | 汇总报告 |
| `cm_doctor` | — | cht-obsidian 自身体检：vault/config/git/索引/GitHub 同步/Harness² CLI |

sweep 常用参数：

```bash
harness2 --bench lab --k 1 --mode parallel \
  --only-domains antitrust-competition --max-tasks 1     # 先小规模试跑
harness2 --bench lab --k 1 --mode parallel --dry-run      # 预览任务流，不调用模型
```

- `--bench`：`jb`（JobBench，职业办公）｜`lab`（LAB，法律）｜`wb`（WorkBuddy-Bench，办公/网页/代码）
- `--subset`：仅 WB 需要，`office`｜`web`｜`code`，setup 之后每条命令都要带
- `--k`：任务级递归预算，越大越强也越贵
- `--mode`：`parallel`（并行探 k 个通用 + k 个领域候选，探得宽）｜`sequential`（连续 k 步精炼，改得深）
- `--substrate`：`oc`（OpenCode，默认）｜`cx`（Codex）
- `--only-domains` / `--max-tasks` / `--split` / `--workers` / `--seed`：任务选择与并发

**judge 与 report 的 bench/substrate/subset/k/mode/seed 必须与 sweep 完全一致**，否则会拒绝评分或找不到结果。

## 4. 结果与恢复

结果写在 `runs/` 下（按基准/子集组织），含任务摘要、交付物、被采纳的外壳、反思笔记与评分。
重跑相同命令可续跑；更换模型或任务选择时用新的 `HARNESS2_RUNS_DIR`。

## 5. 成本与安全（重要）

- **真金白银**：每个任务是 R=4k executor rollout + P=3k improver 会话，`--k` 直接放大成本；
  务必先 `--dry-run`，再 `--max-tasks 1`，最后才放大规模。
- **网络无限制**：执行器网络访问不受限、Codex 沙箱关闭，公开基准的评分标准可能在线可查，
  评测前应按 docs/EXPERIMENTS.md#web-access 配置网络限制，防止"查到答案"。
- **护栏可编辑**：guardrails 只是可编辑文件，不是安全边界；生产使用需自行加网络与权限约束。
- **研究项目**：官方声明"非 Google 官方支持产品"，仓库带免责声明。

## 6. 标准优化循环（常驻指令）

每个涉及 Agent 行为/提示词/工具/流程/代码产出的任务完成后，主动执行：

```
cm_harness2_doctor            # 确认就绪（缺失则输出安装指引后停止）
  → cm_harness2_run(dry_run=true)      # 预览任务流，零成本
  → cm_harness2_run(max_tasks=1)       # 单任务小跑
  → cm_harness2_judge                  # 参数与 sweep 完全一致
  → cm_harness2_report                 # 汇总落盘
  → cm_memory_save / cm_lesson_add     # 经验沉淀回第二大脑（闭环）
```

环境变量：`HARNESS2_CWD`（Harness² 仓库根目录）、`HARNESS2_CMD_RUN/DEMO/SETUP/CHECK/JUDGE/REPORT`（逐个指定 CLI 路径）。
