---
module: 02-mechanism/05-run-inner/04-tools
doc: baseline
status: drafted（代码存在但无设计;❌）
---

# 04-tools — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - `packages/graph-agent/src/graph_agent/core/actions.py`(`ToolDef`/`ToolRegistry` vs `ActionDef`/`ActionRegistry` 两套注册表)
> - `core/graph_assembler.py:479-480`(all_tools 构造 + 手动 bind_tools)
> - `middleware/tool_error.py`(no-op,ToolError 逻辑待实现)、deerflow tool_error_handling_middleware 参考
> - `tools/md_to_json.py`(与 cognitive/md2json 重复,消重)

待填:两套注册表实情 + 混叫现象 + binding 现状(这是 ❌:有代码无设计)。
