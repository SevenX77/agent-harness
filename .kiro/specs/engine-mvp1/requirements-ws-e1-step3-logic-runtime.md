---
ws_id: WS-E1-step3-logic-runtime
modules: [02-mechanism/04-run-outer/01-graph-exec, 01-contract/02-skill-syntax, 01-contract/03-compile-rules]
depends_on: [WS-E1-step2-subagent-dispatch, WS-E6-purity-extensions]
blocks: [WS-E1-step4-iterate, WS-E1-step5-subgraph-io, WS-E2, WS-E5, WS-E8]
owns_files:
  - .kiro/specs/engine-mvp1/requirements-ws-e1-step3-logic-runtime.md
  - packages/graph-agent/src/graph_agent/core/graph_assembler.py
  - packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py
  - packages/graph-agent/tests/core/test_context_facade_logic_action.py
  - packages/graph-agent/tests/core/test_action_registry_v030.py
spec_ssot:
  - docs/engine/mvp1/_impl/IMPL_PLAN.md §四 WS-E1 Step 3
  - docs/engine/mvp1/_impl/WS-E1-create-agent-core.md §5/§6/§7/§8
  - docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md §2/§3/§5/§8
  - docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md §2.3
  - docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md §2.1/§2.3/§4
status: drafted
---

# WS-E1 Step3 LOGIC Runtime Contract — 需求书

## 1. 目标

把 LOGIC phase 的运行时行为从旧的 mutable `Context` facade 收口为 MVP1 的纯 action 契约：action 只读取按 `io.inputs` 切出的输入，返回 dict 作为唯一写回来源；直接 Context mutation 退场。这个步骤是 WS-E1 的串行 Step3，必须先于 iterate 和子图 io 放宽，因为后两者都依赖 LOGIC 已经不再靠隐式黑板 mutation 表达编排和累积。

## 2. SSOT 指针

- 硬约束：MVP1 design / alignment 是绝对真理；旧 live code 和旧测试若冲突，一律视为 drift，代码与测试都必须向 alignment 收敛。
- 目标机制：`docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md` §2 的 LOGIC LE1-3、§5 的 LE1/LE2/LE3。
- 语法契约：`docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md` §2.3，尤其 action 导出函数、入参、返回值、只读输入和纯净性约束。
- 编译/运行错误契约：`docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md` §2.1 purity 校验、§2.3 运行期 LOGIC 节点失败行为、§4 logic domain error codes。
- WS 串行入口：`docs/engine/mvp1/_impl/WS-E1-create-agent-core.md` §7 第 3 步，以及 §8 的 run_skill ordering 约束。
- 现状锚点：`packages/graph-agent/src/graph_agent/core/graph_assembler.py` 的 `_build_logic_node` 当前创建 `Context(data, ...)`，执行 action 后通过 data diff 捕捉 mutation。
- 必读源码：
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`：`_build_logic_node`、`_validate_logic_update_keys`、`_wrap_phase_runtime_node`。
  - `packages/graph-agent/src/graph_agent/cognitive/context_facade.py`：旧 mutable Context facade 形态，只作现状锚点，不是本 WS 必改文件。
  - `packages/graph-agent/src/graph_agent/core/actions.py`：action registry resolve / action definition。
  - `packages/graph-agent/tests/core/test_context_facade_logic_action.py`：旧 Context facade 行为测试，需要被 MVP1 口径替换或删除。
  - `packages/graph-agent/tests/core/test_action_registry_v030.py`：LOGIC return / undeclared output 运行期测试。
  - `packages/graph-agent/tests/core/validators/test_purity_le2.py`：WS-E6 已落的 compile-time purity hard bans，必须保持通过。

## 3. 文件归属

- 本 WS owns：frontmatter `owns_files`。
- 禁止触碰：
  - `packages/graph-agent/src/graph_agent/core/purity.py`、`packages/graph-agent/src/graph_agent/core/error_registry.py`：WS-E6 / WS-E3 范围，本 WS 只回归验证已有 purity 行为。
  - `packages/graph-agent/src/graph_agent/core/loader.py`、`packages/graph-agent/src/graph_agent/core/manifest.py`：iterate / 子图 io 后续步骤范围。
  - `packages/graph-agent/src/graph_agent/middleware/tracing.py`、`packages/graph-agent/src/graph_agent/middleware/tool_error.py`、`packages/graph-agent/src/graph_agent/middleware/loop_detection.py`：WS-E2。
  - `packages/graph-agent/src/graph_agent/core/checkpointer.py`、`packages/graph-agent/src/graph_agent/core/state.py`：WS-E5。
  - `packages/graph-agent/src/graph_agent/middleware/nudge_injector.py`：WS-E8。
  - `apps/studio/**`、`packages/graph-agent-gateway/**`。
- 共享文件协调：`graph_assembler.py` 是 WS-E1 热点文件，本 WS 只处理 LOGIC runtime contract，不并发开启 iterate 或子图 io 的实现分支。

## 4. 现状锚点

当前 LOGIC runtime 仍是旧模型：action 接收 mutable `Context` facade，既可以返回 dict，也可以通过 `context.set` / `context.update` / item assignment 直接改本地 data，再由 `_build_logic_node` 计算 delta 写回。MVP1 目标是反转为纯返回：直接 mutation 不再是合法输出通道。

## 5. 目标行为

- LOGIC action 的运行入参是按该 phase `io.inputs` 从 blackboard 切出的输入视图；action 不应拿到可写黑板 facade，也不应拿到未声明的 blackboard 字段。
- action 链的唯一合法写回来源是每个 action 返回的 dict。
- action 返回 dict 的 key 必须是当前 phase `io.outputs.properties` 的子集；未声明字段继续走现有 `[F-v3-logic-output-field-undeclared]` 运行期 FATAL。
- action 返回非 dict 继续走现有 `[F-v3-logic-action-return-invalid]` 运行期 FATAL。
- 多 action 串行时，前一个 action 的返回结果可以作为后一个 action 的输入增量；这条链路必须显式来自返回值，而不是 Context mutation。
- 旧 Context mutation 路径退场：`set`、`update`、`delete`、item assignment、`setdefault` 这类直接写入不得再使 blackboard 发生隐式写回。旧测试若断言 Context facade 可写，必须删除或改为 MVP1 RED。
- action 尝试直接 mutation 时，不允许出现“测试通过但黑板被偷偷改了”的假绿。具体错误呈现可由实现者决定，但必须可观测地失败或保持 blackboard 不被该 mutation 写入。
- 编译期 purity hard bans 已由 WS-E6 完成：`run_skill`、文件系统访问、`sys.path`、动态 import 越界仍必须命中 `[F-v3-logic-action-purity-violation]`。本 WS 不重新实现 purity，只守住回归。
- 本 WS 不声明 iterate / SUBGRAPH 替代方案已经完成；它只把 LOGIC runtime 的直接 mutation 通道关掉，为后续 Step4 iterate 和 Step5 子图 io 让路。

## 6. 测试要求

- 新增 RED 测试文件建议落点：`packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py`。
- RED 必须覆盖纯返回 happy path：LOGIC action 只通过返回 dict 写出声明的 output，执行结果进入 phase output / final data。
- RED 必须覆盖输入切片：action 只能看见本 phase `io.inputs` 声明的字段，看不见上游或根 blackboard 中未声明字段。
- RED 必须覆盖多 action 链：前一个 action 返回的声明字段能被后一个 action 读取；该传递必须来自返回值。
- RED 必须覆盖 Context mutation 退场：使用旧 `context.set` / `context.update` / item assignment 等写法不能再把字段写入 blackboard，旧 `test_context_facade_logic_action.py` 的 MVP0/MVP0.3 行为断言不能原样保留。
- RED 必须覆盖未声明 output 字段仍然 FATAL，不能因去掉 Context diff 而放松输出边界。
- RED 必须覆盖非 dict return 仍然 FATAL，不能因重构 action 调用而丢失旧错误契约。
- 回归测试必须包含 `packages/graph-agent/tests/core/validators/test_purity_le2.py`，确认 WS-E6 的 run_skill / FS / sys.path / dynamic import hard bans 仍绿。
- 测试不得要求实现 iterate、SUBGRAPH 替代、文件 lazy 注入、artifact 写入或 middleware 后三槽。

## 7. 硬依赖约束

- WS-E1 Step2 subagent dispatch / create_agent 基线必须作为起点；本任务工作区应从 `codex/engine-mvp1-e1-red@c9e363eb` 或其合入后的等价基线开出。
- WS-E6 purity extensions 已在当前基线完成，本 WS 把 run_skill hard ban 当作回归，不再修改 purity 扫描器。
- 本 WS 完成前不得开启 WS-E1 Step4 iterate 或 WS-E1 Step5 subgraph io 的实现，因为三者共享 `graph_assembler.py`。

## 8. 验收标准

- [ ] RED 测试先写，并在当前 baseline 下失败；失败原因必须落在 LOGIC runtime 仍允许 mutable Context / implicit mutation，而不是夹具或环境错误。
- [ ] 旧 MVP0 行为测试不再保留原断言；冲突测试要么删除，要么改成 MVP1 RED。
- [ ] 实现后新增 RED 全绿。
- [ ] `uv run pytest packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_context_facade_logic_action.py packages/graph-agent/tests/core/test_action_registry_v030.py packages/graph-agent/tests/core/validators/test_purity_le2.py -q` 通过。
- [ ] `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/e2e/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_purity_le2.py packages/graph-agent/tests/runner/test_v030_error_contract_v2_diagnostics.py -q` 继续通过。
- [ ] `uv run mypy packages/graph-agent/src/graph_agent/core/graph_assembler.py` 通过。
- [ ] `git diff --check` 无输出。
- [ ] 如果 `uv.lock` 被 `uv run` 摸脏且本 WS 没有依赖变更，必须恢复。
- [ ] forbidden files 无 diff，尤其不改 `purity.py`、`loader.py`、`manifest.py`、middleware 后三槽、Studio 和 gateway。

## 9. 不做

- 不实现 iterate：节点级 loop accumulate、图级 batch、图级 loop-B 都归 WS-E1 Step4。
- 不实现子图 io inputs 放宽；归 WS-E1 Step5。
- 不实现文件 lazy 注入、artifact business_data_md 或 InputFileInjectedEvent emit；归 WS-E1-io / WS-E2 / E5 之后的工作。
- 不修改 purity 扫描器；WS-E6 已完成，本 WS 只回归验证。
- 不修改 error registry 元数据形状；错误契约 V2 后续阶段归 WS-E3。
- 不清理所有历史 Context facade API；只确保 LOGIC runtime 不再依赖它作为写回通道。

## 10. baseline 回写指令

实现落地后，按真实代码回写：

- `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md`：LOGIC runtime 是否已从 mutable Context diff 改为纯返回契约。
- `docs/engine/mvp1/01-contract/02-skill-syntax/baseline.md`：若 baseline 中仍记录旧 Context action 形态，需要改为真实 action 入参/返回现状。
- `docs/engine/mvp1/01-contract/03-compile-rules/baseline.md`：只在错误码或 purity 现状确实变化时更新；若只是回归确认 WS-E6 行为，不改。
- `docs/engine/mvp1/_impl/IMPL_PLAN.md`：仅在 PM 要求维护进度面板时，把 WS-E1 Step3 标成完成；不要提前把 Step4/Step5 写成完成。

## 11. 评审检查点

- 契约门：Claude 审 RED 是否忠实编码“纯返回、只读 inputs、Context mutation 退场、输出边界不放松”，并确认没有越界要求 iterate / subgraph io / middleware。
- Codex 审查退出：§8 全部满足，且旧 MVP0 行为断言没有残留。
- Claude 终审：目标是否真正从“action 可改黑板”转为“action 只能返回 dict”；baseline 是否只在实现后按真实代码回写。

## 12. 给 Codex 的交接：按写作规范写 kiro task.md

契约门通过后，Codex 据已批准 RED 测试写实施任务书，落点建议为 `.kiro/specs/engine-mvp1/task-ws-e1-step3-logic-runtime.md`，并同步输出给 Gemini 的可复制 prompt。交接约束：

- 来源只能是已批准测试、`spec_ssot` 和本需求书，不凭空扩大到 iterate、子图 io、middleware、checkpoint 或 Studio。
- `task.md` 使用 Phase 分段和 `- [ ]` 勾选项，每项挂 `_Requirements: WS-E1-step3-logic-runtime` 并写明验证命令。
- frontmatter 指回本需求书、alignment SSOT、`owns_files` 和 forbidden files；不得重写设计文档内容。
- 行号只允许作为执行者落地时重新核实的 grounding，不写成编辑坐标。
- 不跑 `/kiro:spec-tasks` 自动生成，避免 clobber 现有任务文件。
- Gemini prompt 必须包含工作区路径、分支、RED 命令/失败摘要、允许修改文件、禁止触碰文件、目标契约、验证命令和回报格式。
