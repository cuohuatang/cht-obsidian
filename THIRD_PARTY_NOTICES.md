# Third-Party Notices

## Harness² MCP wrapper（cuohuatang/harness2）

`src/cut_obsidian_mcp/modules/harness.py`、`src/cut_obsidian_mcp/references/harness2-usage.md`
与 `scripts/harness2_doctor.sh` 移植自 [cuohuatang/harness2](https://github.com/cuohuatang/harness2)
的 harness2-mcp 与 skill 部分，依据 **Apache License 2.0** 使用。

- 上游许可证全文：https://www.apache.org/licenses/LICENSE-2.0
- 上游所包装的 Harness² 本体（Google Research）同为 Apache-2.0：
  https://github.com/google-research/harness2
- 本仓库主体为 MIT 许可；上述文件保留 Apache-2.0 许可与署名。

Apache License 2.0 要点：保留版权声明与许可副本、注明修改、携带 NOTICE 文件（如有）。
本次移植的修改：工具名加 `cm_harness2_` 前缀、新增 `self_doctor()` 自体检与
`STANDING_ORDERS` 闭环沉淀条目、手册增加 cht-obsidian 集成说明。
