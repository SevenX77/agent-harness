---
module: 03-finish-task-validation
doc: baseline
status: drafted
last_verified: 2026-06-02
---
<!-- 核对进度:已迁 7 块 / 未迁 0 块 / 2026-06-04 -->

~~# 03-finish-task-validation — Baseline(现状)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/baseline.md#后端功能)

核心结论：语义错/结构错分流机制没有丢，丰富版还在 `tools/md_to_json.py`；但 live finish_task 接的是 `cognitive/md2json.py` 简化版，所有 validation error 都会走 `cognitive/finish_task.py` 的 patch loop。这样会把“评分:好”这类语义错错误送进格式修复，存在补假值风险。

~~## 覆盖范围~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/baseline.md#后端功能)

覆盖范围：本文覆盖决策记录 §5 与 Q1 核心。

| 覆盖目标 | 现状范围 | 覆盖说明 |
|---|---|---|
| 丰富版 `tools/md_to_json.py` | `packages/graph-agent/src/graph_agent/tools/md_to_json.py:81-181`、`packages/graph-agent/src/graph_agent/tools/md_to_json.py:284-604` | 有 ParsedBlock、DiagnosticReport、semantic_only、SemanticValidationError、md-patch 分流。 |
| 简化版 `cognitive/md2json.py` | `packages/graph-agent/src/graph_agent/cognitive/md2json.py:13-185` | 只做 markdown dict 解析和 jsonschema errors，没有 semantic/structural 分类。 |
| live 接线 | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:32-33`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py:636-647` | finish_task 当前接 `parse_finish_markdown` 简化版。 |
| patcher | `packages/graph-agent/src/graph_agent/cognitive/md_patch.py:59-84` | prompt 只要求格式和机械类型修复。 |
| git 溯源 | `git log --follow` 结果 | `tools/md_to_json.py` 可追到 `c7405b7e`；`cognitive/md2json.py` / `finish_task.py` 是 `a53e72ca` 新增。 |

~~## 编号执行流程(现状)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/baseline.md#后端功能)

1. 丰富版 `ParsedBlock`(用途：把每个 markdown ## 块拆成 meta 和用户字段)把 `meta.id` 与 `data` 分开，避免 Pydantic 看到 framework metadata，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:88-99`。

2. 丰富版 `FieldError` 有 `error_kind: Literal["structural","semantic"]`，默认 semantic，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:102-109`。

3. 丰富版 `DiagnosticReport.semantic_only`(用途：判断是否全部错误都是 semantic)在有错误且没有 structural errors 时为真，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:120-142`。

4. 丰富版 `SemanticValidationError` 明确说明 md-patch 不能修 semantic errors，例如 int 期望却输出“极高”，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:171-181`。

5. 丰富版 `parse_md`(用途：把 structured Markdown 解析成 `ParsedBlock` 列表)按 `##` 分块、抽字段、按 schema 类型做基础 coercion，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:284-307`。

6. 丰富版 `diagnose`(用途：逐 item Pydantic validate)把 Pydantic errors 转成 `FieldError`，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:454-491`。

7. 丰富版 `_classify_error_kind` 当前把 `missing` 判为 structural，其余判为 semantic，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:444-448`。

8. 丰富版 `md_to_json`(用途：parse + diagnose + patch 的统一入口)在全合格时直接返回 validated models，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:515-557`。

9. 丰富版 `md_to_json` 在 `report.semantic_only` 时跳过 md-patch，抛 `SemanticValidationError`，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:559-567`。

10. 丰富版 `md_to_json` 只有在存在 structural errors 时才抽取失败块并调用 `run_skill(md-patch)`，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:568-604`。

11. 丰富版 `schema_to_type_dict`(用途：把 Pydantic 字段转成可给 LLM 的字段约束说明)能输出 int/float/list/Literal 等约束，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:675-684`。

12. 简化版 `Md2JsonResult` 只有 `data`、`validation_errors`、`repaired` 三个字段，没有 error_kind 或 semantic_only，见 `packages/graph-agent/src/graph_agent/cognitive/md2json.py:13-20`。

13. 简化版 `parse_finish_markdown` 用 `_parse_markdown_to_dict` 先转 dict，再用 `Draft202012Validator.iter_errors` 产生 jsonschema errors，见 `packages/graph-agent/src/graph_agent/cognitive/md2json.py:26-38`。

14. 简化版 `_coerce_value` 会尝试 int/float/bool coercion；失败时保留原字符串，见 `packages/graph-agent/src/graph_agent/cognitive/md2json.py:88-128`。

15. live `graph_assembler` 从 `graph_agent.cognitive.md2json` import `parse_finish_markdown`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:32-33`。

16. `_build_agent_finish_task_tool` 把 `parse_finish_markdown` 传给 `build_finish_task_tool`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:636-647`。

17. `build_finish_task_tool` 对任何 validation_errors 都进入 patch loop，只要 patcher 可用且 output_schema 存在，见 `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:49-93`。

18. `LLMMdPatchClient.patch` 的 prompt 明确是“Fix only formatting and mechanical type issues”，见 `packages/graph-agent/src/graph_agent/cognitive/md_patch.py:74-82`。这说明它不是语义重生成器。

19. git 溯源：`git log --follow -- packages/graph-agent/src/graph_agent/tools/md_to_json.py` 显示该文件历史可追到 `c7405b7e feat: merge Story Forge features into Agent Harness`；`git log --follow -- packages/graph-agent/src/graph_agent/cognitive/md2json.py` 与 `finish_task.py` 显示 `a53e72ca feat(graph-agent v2.1): hard cutover ...` 新增了两者。

~~## Baseline / Alignment 差异~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/baseline.md#后端功能)

baseline 并存两套 md2json：丰富版有 semantic/structural 分流但 live 未接；简化版 live 在用但无法区分语义错和结构错。alignment 目标是 finish_task 接回丰富版 `tools/md_to_json.py:md_to_json()` 的决策逻辑。

~~## 决策原因~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/baseline.md#后端功能)

“评分:int，模型输出评分:好”是语义错，不是格式错。格式 patcher 无法知道“好”应等于几分；如果送进 patcher，可能补出一个看似合法但没有事实依据的数字。丰富版 `SemanticValidationError` 已经把这类错误定义为应打回主 agent 重生成，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:171-181`。

当前 live 接错线的直接证据是 `graph_assembler.py` 引入并使用 `cognitive/md2json.py`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:32-33`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py:642-645`。

~~## 代码索引(clues)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/baseline.md#后端功能)

- `packages/graph-agent/src/graph_agent/tools/md_to_json.py:515-604`: rich md_to_json 决策入口。
- `packages/graph-agent/src/graph_agent/cognitive/md2json.py:26-38`: live 简化版入口。
- `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:49-93`: 当前统一 patch loop。
- `packages/graph-agent/src/graph_agent/cognitive/md_patch.py:74-82`: patcher 只修格式和机械类型。

~~## 待办/疑点~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/baseline.md#后端功能)

1. 待办：写 failing test，复现 semantic-only 错误不得调用 md-patch。
2. 待办：finish_task 接回 `tools/md_to_json.py:md_to_json()`，并把 `SemanticValidationError` 转为给主 agent 的 error ToolMessage。
3. 待办：退役或合并 `cognitive/md2json.py`，避免双 md2json 继续漂移。

