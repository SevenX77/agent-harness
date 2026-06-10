---
ws_id: WS-E1-step5-subgraph-io
modules:
  - 11-io
  - 02-mechanism/04-run-outer/01-graph-exec
  - 01-contract/02-skill-syntax
  - 01-contract/03-compile-rules
depends_on:
  - WS-E1-step4-iterate-runtime
blocks:
  - WS-E1-io
owns_files:
  - .kiro/specs/engine-mvp1/requirements-ws-e1-step5-subgraph-io.md
  - packages/graph-agent/src/graph_agent/core/loader.py
  - packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py
  - packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py
  - packages/graph-agent/tests/e2e/test_round14_compiler_e2e.py
  - packages/graph-agent/spec/features.yaml
  - packages/graph-agent/tests/fixtures/round28/valid_features_primary_owners.yaml
  - packages/graph-agent/tests/fixtures/round28/valid_features_runtime_compat.yaml
spec_ssot:
  - docs/engine/mvp1/_impl/IMPL_PLAN.md
  - docs/engine/mvp1/_impl/WS-E1-create-agent-core.md
  - docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md
  - docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md
  - docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md
  - docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md
status: drafted
---

# WS-E1 Step5 Subgraph IO Relaxation 需求书

## 1. 目标

把 WS-E1 串行链推进到 Step5: 只收敛 11-io 的子图 inputs 放宽。子图节点像普通节点一样通过 StateMapper 从父图 blackboard 切片输入；父 `SUBGRAPH.md io.inputs` 与子 `GRAPH.md io.inputs` 不再要求 1:1 完全相等。`io.outputs` 仍是父子边界契约,必须继续严格校验,不一致仍报 `[F-v3-subgraph-io-mismatch]`。

## 2. SSOT 指针

- 目标唯一真理: `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md` §2/§5 的 E1 子图 io 放宽。
- 语法唯一真理: `docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md` §2.4.3 和 §2.10.2。
- 编译规则背景: `docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md` 的 subgraph domain 错误码。
- 现状起点: `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md` §5,当前 loader 对 inputs 和 outputs 都做 1:1 强校。
- WS 串行入口: `docs/engine/mvp1/_impl/WS-E1-create-agent-core.md` §5/§6/§7 的 11-io 收敛说明。
- 必读源码:
  - `packages/graph-agent/src/graph_agent/core/loader.py`: `_validate_subgraph_io_contracts`。
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`: `_wrap_phase_runtime_node`、`_build_subgraph_node`,只作运行时 grounding。
  - `packages/graph-agent/src/graph_agent/runtime/state_mapper.py`: `StateMapper.build_phase_input` / `wrap_phase_output`。
  - `packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py`: 旧 inputs mismatch 断言。
  - `packages/graph-agent/tests/e2e/test_round14_compiler_e2e.py`: round14 mismatch 变体。

判准铁律: MVP1 design/alignment 是绝对真理。旧 live code 或旧测试如果还断言 MVP0 的子图 inputs 1:1,视为 drift;冲突测试必须删除或改成 MVP1 RED。

## 3. 文件归属

- 本 WS owns: frontmatter `owns_files` 所列文件。
- `loader.py` 只允许处理 `_validate_subgraph_io_contracts` 的子图 IO 契约,不得顺手改 loader 的 resolver、agent reference、iterate、purity 或 deprecated physical IO 逻辑。
- `graph_assembler.py`、`state_mapper.py` 仅作 grounding。若 RED 显示运行时仍有缺口,必须先回报并重新确认范围,不得在本契约门阶段直接扩大 owns。
- 禁止触碰:
  - `packages/graph-agent/src/graph_agent/core/runner.py`
  - `packages/graph-agent/src/graph_agent/io/**`
  - `packages/graph-agent/src/graph_agent/tools/builtin/read_file.py`
  - `packages/graph-agent/src/graph_agent/callbacks/events.py`
  - `packages/graph-agent/src/graph_agent/callbacks/emit.py`
  - `packages/graph-agent/src/graph_agent/middleware/**`
  - `packages/graph-agent/src/graph_agent/core/checkpointer.py`
  - `packages/graph-agent/src/graph_agent/core/state.py`
  - `apps/studio/**`
  - `packages/graph-agent-gateway/**`

## 4. 现状锚点

当前 `loader._validate_subgraph_io_contracts` 编译期递归加载子图后,同时比较父 `SUBGRAPH.md` 与子 `GRAPH.md` 的 `io.inputs` 和 `io.outputs`。任一 schema 不完全相等都会 fatal `[F-v3-subgraph-io-mismatch]`。这保留了 MVP0 的 inputs 1:1 模型,与 MVP1 的 blackboard slice 语义冲突。

## 5. 目标行为

- 父 `SUBGRAPH.md io.inputs` 与子 `GRAPH.md io.inputs` 字段集合、required 集合或同名 schema 不一致时,编译期不得仅因 inputs mismatch 报 `[F-v3-subgraph-io-mismatch]`。
- 父 `SUBGRAPH.md io.inputs` 是子 `GRAPH.md io.inputs` 的超集时,只要父黑板里有子图运行需要的字段,子图应能运行并产出声明 outputs。
- 父 `SUBGRAPH.md io.inputs` 与子 `GRAPH.md io.inputs` 是不同集合时,compile 仍应放行。运行期如果子图真正需要的字段不在父图切片里,由运行期 state mapping 或子节点自身错误暴露,不在 loader 做镜像强制。
- 父 `SUBGRAPH.md io.outputs` 与子 `GRAPH.md io.outputs` 必须继续严格一致。outputs 不一致仍在编译期 fatal,错误码仍是 `[F-v3-subgraph-io-mismatch]`。
- 本步骤不得放宽 outputs,不得引入 alias/mapping 语法,不得新增文件导入或 artifact 行为。

## 6. 测试要求

Codex 必须先写 RED,并覆盖:

- 父 `SUBGRAPH.md io.inputs` 是子 `GRAPH.md io.inputs` 的超集时,compile 不应因 inputs mismatch fatal。
- 父 `SUBGRAPH.md io.inputs` 与子 `GRAPH.md io.inputs` 是不同集合时,compile 不应因 inputs mismatch fatal。
- 运行时父 blackboard 里有子图需要的字段,子图能在父 `SUBGRAPH.md io.inputs` 非 1:1 的情况下跑通,并证明子图 action 只看见自己声明的输入切片。
- 父子 `io.outputs` 不一致仍 fatal,错误码仍是 `[F-v3-subgraph-io-mismatch]`,并且失败信息应能看出是 outputs mismatch。
- 旧 `test_subgraph_io_input_mismatch_is_rejected_at_compile_time` 或等价 e2e inputs mismatch 断言不得原样保留;必须改成 MVP1 RED 或改为 outputs mismatch。

## 7. 硬依赖约束

- 依赖 WS-E1 Step4 已完成。Step5 从 `d38f57eb feat(engine): add iterate runtime contracts` 后的 clean worktree 开始。
- 本步骤在契约门前只写 requirements 和 RED 测试。RED 失败形状应落在 `loader._validate_subgraph_io_contracts` 仍强校 inputs,不要提前写 implementation task/Gemini prompt。
- 契约门通过后,再据已批准测试写 task 和 Gemini prompt,然后才允许实现。

## 8. 验收标准

- [ ] 当前 worktree/分支/HEAD 已核实。
- [ ] RED 测试先写,并在当前 baseline 下失败;失败原因必须落在 loader 仍强校 inputs,不是夹具、resolver 或环境问题。
- [ ] outputs mismatch RED 保持 fatal 预期,不把 outputs 放宽。
- [ ] 旧 inputs 1:1 断言已经替换或删除,没有残留 MVP0 断言。
- [ ] 契约门前不写 `.kiro/specs/engine-mvp1/task-ws-e1-step5-subgraph-io.md` 或 Gemini prompt。
- [ ] 契约门前不修改生产实现文件。
- [ ] 没有触碰 forbidden files。
- [ ] `uv.lock` 如被 `uv run` 摸脏且本 WS 没有依赖变更,必须恢复。

## 9. 不做

- 不做文件导入 lazy。
- 不做 artifact / `business_data_md`。
- 不做 `InputFileInjectedEvent` emit 接线。
- 不做 runner / io / read_file / storage 改动。
- 不碰 callbacks/events、callbacks/emit、middleware、checkpointer/state、Studio、gateway。
- 不修 `graph_assembler.py` ruff hygiene 债。
- 不写 task/Gemini prompt,直到 Claude 过契约门。

## 10. baseline 回写指令

实现落地后按真实代码回写:

- `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md`: 子图 inputs 是否已放宽、outputs 是否仍严校。
- 如测试或契约映射从旧 MVP0 inputs mismatch 改为 MVP1 行为,同步相关测试 traceability fixture,但不回写 MVP0 文档。
- `docs/engine/mvp1/_impl/IMPL_PLAN.md`: 仅在 PM 要求维护进度面板时更新 Step5 状态。

## 11. 评审检查点

- 契约门: Claude 审 RED 是否忠实编码“inputs 放宽、outputs 不放宽、子图按黑板切片运行”,并确认没有越界到 E2/E3/runner/io。
- Codex 审查退出: 以 §8 全满足为准。
- Claude 终审: 查实现是否只改 loader inputs 校验、baseline 是否诚实、旧 MVP0 inputs 断言是否无残留。

## 12. 给 Codex 的交接

契约门通过后,再据已批准 RED 写 `.kiro/specs/engine-mvp1/task-ws-e1-step5-subgraph-io.md` 和 Gemini prompt。task/prompt 必须包含工作区路径、分支、RED 命令/失败摘要、owns_files、禁止触碰、目标契约、验证命令和回报格式。禁止在 RED 未过契约门前写 task 或实现。
