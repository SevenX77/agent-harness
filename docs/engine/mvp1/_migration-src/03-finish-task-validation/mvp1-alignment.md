---
module: 03-finish-task-validation
doc: mvp1-alignment
status: drafted
last_verified: 2026-06-02
---
<!-- 核对进度:已迁 7 块 / 未迁 0 块 / 2026-06-04 -->

~~# 03-finish-task-validation — MVP1 Alignment(目标设计)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

MVP1/V4 决策：finish_task 校验流水线接回 `tools/md_to_json.py` 的丰富版 `md_to_json()`，恢复三态分流：全合格直接通过；结构错走 surgical md-patch；语义错打回主 agent 重生成，绝不交给 patcher 猜值。

~~## 覆盖范围~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

覆盖范围：本文覆盖 finish_task 校验路由、语义/结构错分流、错误码边界、git 溯源。

| 范围 | MVP1 目标 |
|---|---|
| `tools/md_to_json.py:md_to_json` | 成为 finish_task schema 校验主入口。 |
| `tools/md_to_json.py:SemanticValidationError` | semantic-only 错误变成主 agent 的 retry feedback。 |
| `cognitive/md2json.py` | 退役或收敛为兼容 facade，不再作为 live 决策入口。 |
| `cognitive/md_patch.py` | 只处理 structural/mechanical repair，不处理 semantic regeneration。 |

~~## 目标设计与编号流程~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

1. finish_task 收到 markdown 后，先根据 phase output schema 得到 Pydantic model。丰富版 `md_to_json` 的入参是 `md_text`、`schema: type[BaseModel]`，以及必填关键字参数 `skill_resolver`，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:515-520`。MVP1 适配器必须从 graph assembly 已有 `skill_resolver` 依赖传入该参数，不能退回全局查找。

2. `md_to_json` 调 `parse_md` 得到 blocks，再调 `diagnose` 得到 `DiagnosticReport`，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:545-550`。

3. 如果 `report.all_valid`，直接返回 validated Pydantic model list，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:556-557`。

4. 如果 `report.semantic_only`，抛 `SemanticValidationError(report)`，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:559-567`。MVP1 决策：该异常转成 `ToolMessage(status="error")` 或 `Command(goto="model")` 的反馈，要求主 agent 重写对应字段。

5. 如果存在 structural errors，`md_to_json` 只抽取失败的 `##` blocks，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:568-572`。MVP1 决策：这条路径保留 surgical patch，避免重写全部有效内容。

6. structural path 调用 bundled `md-patch` skill，并把 `valid_results`、`error_items`、`schema` 一起传入，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:578-589`。

7. patch 完成后只对 `final_results` 再做 `schema_cls.model_validate`，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:599-604`。MVP1 决策：patcher 仍受 Pydantic 兜底，不信任纯文本。

8. `SemanticValidationError` 的 report 文本应原样或结构化进入 retry feedback。`DiagnosticReport.to_prompt_string` 已把 structural 和 semantic 分开描述，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:144-168`。

9. `cognitive/md2json.py` 退役时不能直接删测试覆盖；需要将兼容测试迁到丰富版 facade，证明 `Md2JsonResult` 调用方已不再需要。当前简化版导出见 `packages/graph-agent/src/graph_agent/cognitive/md2json.py:185`。

10. 业务规则错仍由 `CognitiveFlowMiddleware._run_business_validator` 处理。它在 Pydantic 通过后运行 phase validator，失败时返回 `[Business]` 前缀错误，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:584-596`、`packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:637-680`。

~~## 已实现 / 与 baseline 差异~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

已实现：丰富版 `md_to_json`、semantic-only 判断、surgical patch、schema_to_type_dict 都在 `tools/md_to_json.py`，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:515-684`。

未实现：live finish_task 仍接 `parse_finish_markdown` 简化版，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:642-645`。

未实现：semantic-only 错误还没有统一转成 agent retry feedback；当前 `build_finish_task_tool` 只看 `validation_errors`，见 `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:49-93`。

~~## 决策原因~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

接回 rich md_to_json 是为了化解 finish_task 校验路由冲突：格式修复只适合 structural errors，semantic errors 必须由主 agent 根据业务上下文重新生成。代码已有 `SemanticValidationError` 正是这个设计的残留证据，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:171-181`。

保留 surgical patch 是为了兼容弱模型输出脏 markdown 的现实，不把所有 schema fail 都升级成重生成；`_extract_md_excerpt` 只抽失败 blocks，见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:497-512`。

退役简化版是为了减少错误码和输出格式冲突。两套 parser 对同一 markdown 的 coercion、error shape 和 patch 策略不同，继续并存会让 finish_task 行为不可解释。

~~## 代码索引(clues)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

- `packages/graph-agent/src/graph_agent/tools/md_to_json.py:140-142`: semantic_only 判断。
- `packages/graph-agent/src/graph_agent/tools/md_to_json.py:559-567`: semantic-only 跳过 patch。
- `packages/graph-agent/src/graph_agent/tools/md_to_json.py:578-589`: structural path 调 md-patch。
- `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:637-680`: schema 后业务 validator。

~~## 待办/疑点~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

1. 待办：实现适配器，把 `md_to_json()` 的 list[BaseModel] 结果转成 finish_task/CognitiveFlow 所需的 BusinessData 写入形态。
2. 待办：补测试覆盖 semantic-only、structural-only、mixed errors 三类路由。
3. 疑点：mixed errors 是否先 patch structural 再把 semantic 打回，还是全部打回主 agent。当前 rich 代码只在 semantic_only 时抛，mixed 会走 patch；MVP1 实现前应明确是否保留这个行为。
