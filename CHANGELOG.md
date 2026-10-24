# CHANGELOG

## 0.6.0 · 2026-10-25
**新增（Harness² 嫁接）**
- 移植 cuohuatang/harness2（Apache-2.0，Google Research Harness² 框架的 MCP 封装）为内置模块 `modules/harness.py`：
  - `cm_harness2_doctor/demo/setup/check/run/judge/report` 7 工具：包装 Harness² 6 个 CLI 入口（递归优化 sweep：先 dry_run 预览 → max_tasks=1 小跑 → judge → report），CLI 缺失时返回安装指引而非报错；单次输出超 2 万字符自动截断
  - `cm_doctor`：cht-obsidian 自身一键体检（vault 可写 / config 0600 / git / 索引 / GitHub 同步配置 / Harness² CLI），分级报告 + 修复建议
  - `harness2://usage` MCP 资源：完整使用手册随连接可取
  - MCP instructions 增加 Harness² 常驻指令（触发时机 / 成本闸门 / 参数一致性 / 故障处理 / 闭环沉淀 / 保密铁律）
- 经验闭环：优化循环产出的"被采纳外壳 + 有证据经验"经 cm_memory_save / cm_lesson_add 沉淀回第二大脑（记忆库 × 优化器）
- 新增 `scripts/harness2_doctor.sh` 裸机体检脚本与 `THIRD_PARTY_NOTICES.md` 署名文件

**变更**
- 工具总数 26 → 34；测试 39 → 56 项全绿；版本 0.5.1 → 0.6.0
- 定位说明：云端多用户版默认不装 Harness² CLI（每用户需自带模型凭证），完整功能在本地 stdio 模式使用

## 0.5.1 · 2026-10-24
**新增**
- 用户控制台改版「入库/出库」双卡片：📥 入库（✍️ 手动记录 / 🤖 从 Agent 采集 / 💬 从微信采集，自动拆条即存即推），📤 出库（仓库绑定 / 立即推送 / 钥匙管理）
- 出库高级区支持自定义推送凭证：`/api/app/key` 保存 GitHub Token 或 SSH 私钥（0600 保密、格式校验、整体替换）；无 token 时 `github_sync` 自动走 git@ SSH 协议并注入 `GIT_SSH_COMMAND`
- 采集入库接口 `/api/app/import`：Agent 源递归提取 JSON 文本、微信源按空行/日期自动切分，单次上限 50 条
- 部署包补入 `deploy.sh` 一键部署脚本与部署 README

**修复**
- 入库接口字段对齐前端（`text`/`content` 双兼容），响应补 `imported` 计数

**变更**
- 版本 0.5.0 → 0.5.1；测试 35 → 39 项全绿

## 0.3.0 · 2026-10-23
**新增**
- 第二大脑模块（6 个新工具）：`cm_brain_process` 一键消化管线（收集→聚类→提炼→工作流页→打标签→双链→MOC）、`cm_brain_finalize` 会话终结一键（周总结+技能建议+消化+上传）、`cm_brain_moc`、`cm_brain_status`
- GitHub 私有仓库实时同步（4 个新工具）：`cm_github_setup/push/pull/status`，token 仅存本地 0600 文件，输出全程脱敏
- 多 Agent 分空间：`agent`/`category` 参数（记忆/踩坑/纠错），第二大脑按 Agent 隔离并聚合
- 06-第二大脑 目录 + MOC 导航页（Obsidian 双链自动聚合）

**修复**
- 正式安装与源码开发分离：开发期回退 editable 安装

**变更**
- 工具总数 18 → 26；版本 0.3.0

## 0.2.0 · 2026-10-11
**新增**
- 会话交接 3 工具（六段式 handoff，未答问题转问）；技能沉淀 2 工具（suggest 自动提示 + propose 真实提炼草稿）

**修复**
- read_note_by_id 兼容 ID/路径；memory.save 同日覆盖改为独立文件

**变更**
- 工具总数 13 → 18

## 0.1.0 · 2026-10-08
**新增**
- 13 工具：记忆（jieba+FTS5 中文检索、BM25+TF-IDF 混合）、踩坑本、纠错台账、经验总结（纯规则）、Obsidian 嫁接（vault 默认 ~/.cuohuatang/vault 可编辑、双链约定）
- GitHub 公开仓库发布，tag v0.1.0
