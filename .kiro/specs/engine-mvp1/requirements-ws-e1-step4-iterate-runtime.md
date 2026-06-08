---
ws_id: WS-E1-step4-iterate-runtime
modules:
  - 02-mechanism/04-run-outer/02-iterate
  - 01-contract/02-skill-syntax
  - 01-contract/03-compile-rules
  - 02-mechanism/04-run-outer/01-graph-exec
depends_on:
  - WS-E1-step3-logic-runtime
blocks:
  - WS-E1-step5-subgraph-io
  - WS-E1-io
  - WS-E5-checkpoint-inner
owns_files:
  - packages/graph-agent/src/graph_agent/core/manifest.py
  - packages/graph-agent/src/graph_agent/core/loader.py
  - packages/graph-agent/src/graph_agent/core/graph_assembler.py
  - packages/graph-agent/src/graph_agent/core/error_registry.py
  - packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py
spec_ssot:
  - docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/mvp1-alignment.md
  - docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md
  - docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md
  - docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md
status: drafted
---

# WS-E1 Step4 Iterate Runtime — 需求书

## 1. 目标

把 WS-E1 串行链推进到 Step4:声明式 `iterate` 执行。目标是让 MVP1 的循环原语从文档契约进入 engine runtime:节点级 batch/range、节点级 loop accumulate、图级 batch、图级 loop=B。Step3 已把 LOGIC action 收口成纯返回 dict;Step4 要把循环、累积、批处理从 action 手写搬回声明式 runtime。

## 2. SSOT 指针

- 目标唯一真理:`docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/mvp1-alignment.md` §1-§8。
- 语法唯一真理:`docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md` §2.9,以及同文档对子图继承的说明。
- 编译规则唯一真理:`docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md` 的 iterate 错误码要求。
- graph exec 背景:`docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md` 的 LOGIC/action 边界、StateMapper 与子图/iterate 分工。
- 现状起点:`docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/baseline.md`。当前只有旧 `batch` live;loop、图级、range、统一 `iterate` 都未落代码。
- 必读源码:
  - `packages/graph-agent/src/graph_agent/core/manifest.py` 的 `BatchSpec` 与 phase AST 共享字段。
  - `packages/graph-agent/src/graph_agent/core/loader.py` 的 phase frontmatter normalizer 和 AST 构造。
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py` 的 `_resolve_iterator`、`_build_batch_wrapped_node`、`_wrap_phase_runtime_node`、`assemble_graph`。
  - `packages/graph-agent/src/graph_agent/runtime/state_mapper.py` 的 phase input/output 切片与合并。

**判准铁律:** MVP1 design/alignment 是绝对真理。旧 live code 或旧测试如果还断言 MVP0 行为,视为 drift;冲突测试不得保留旧断言,必须删除或改成 MVP1 RED。

## 3. 文件归属

- 本 WS owns:frontmatter `owns_files` 所列文件。
- `error_registry.py` 只允许增补 `[F-v3-iterate-*]` 错误码 metadata,不得顺手做错误契约 V2 的 `details` / `diagnostics` / 定位轴 / doc registry 等其他扩展。
- 禁止触碰:
  - `packages/graph-agent/src/graph_agent/core/checkpointer.py`、`packages/graph-agent/src/graph_agent/core/state.py`:归 WS-E5。
  - `packages/graph-agent/src/graph_agent/middleware/tracing.py`、`tool_error.py`、`loop_detection.py`:归 WS-E2。
  - `packages/graph-agent/src/graph_agent/callbacks/events.py`、`emit.py`:WS-E4 已完成 schema-only;Step4 不接真实 trace emit。
  - `packages/graph-agent/src/graph_agent/core/runner.py`、`packages/graph-agent/src/graph_agent/io/*`、`packages/graph-agent/src/graph_agent/tools/builtin/read_file.py`:归 WS-E1-io 或后续 IO 工作。
  - `apps/studio/**`、`packages/graph-agent-gateway/**`。
- 共享文件协调:`graph_assembler.py` 是 WS-E1 热点文件,本 WS 只能从 PR #116 后的 Step3 基线单线推进,不要与 Step5 或 WS-E1-io 并行编辑同一 worktree。

## 4. 现状锚点

现状只有旧 `batch` 字段可用:节点级并行 map,无 range,无统一 `iterate`,无节点级 loop accumulate,无图级 batch,无图级 loop=B。旧 action 内手写循环或 `run_skill` 不是 MVP1 目标,不能当 runtime 行为的替代方案。

## 5. 目标行为

- phase frontmatter 接受统一 `iterate` 声明,并继续兼容旧 `batch` 声明。旧 `batch` 与 `iterate.mode=batch` 不得产生两套互相矛盾的运行语义。
- 节点级 batch 按 `iterate.over` 取列表,按 `item_var` 注入每项,尊重 `concurrency`,并把每项输出聚合回黑板。声明 `range` 时按 1-based 闭区间只运行范围内的 item。
- 节点级 loop 串行执行。每轮输入包含当前 item 与累积变量;每轮输出按 `accumulate.from` 取值,用声明的 merge 语义更新累积变量;最终把 `accumulate.var` 写回黑板。
- `accumulate.merge` 至少覆盖 MVP1 文档列出的 append、extend、merge、replace。每种 merge 的输入/输出形状必须可测、错误时必须给出 V4 fatal,不能静默吞掉。
- loop 节点的 `io.inputs` 必须声明 `item_var` 与 `accumulate.var`;缺失时编译期 fatal,错误码归 iterate 域。
- `iterate.over` 指向的值必须是 list;不是 list 时 fatal,错误码归 iterate 域。空 list 的行为必须可预测:batch/loop 都不应调用节点体;batch 返回声明输出字段的空聚合,loop 返回 `accumulate.init`。
- 图级 batch 是整张 DAG 的 fan-out,每个 item 一次图执行实例,各实例状态隔离,最终按图输出聚合。
- 图级 loop=B:引擎把 DAG 包成 loop-body,同一 thread 串行多轮,每轮使用 `checkpoint_ns=iter{k}` 风格的轮次归属;不得退化成 runner 外层 N 次独立 invoke。实现必须暴露可测试的单 thread / `iter{k}` 或等价结构性信号,让 RED 能证明图级 loop 是一次 `graph.invoke` 内部 loop-body,不是 runner/test 外层 N 次独立 invoke。
- Step4 不负责真实 trace emit 接线。每轮 trace 盖 `phase_execution_id` / `iteration_index` 属 observability 后续消费;Step4 RED 只需锁住 runtime 能提供轮次归属所需的结构性入口,不改 callbacks/events。

## 6. 测试要求

Codex 必须先写 RED,并覆盖:

- manifest/loader 能解析 `iterate` 声明;旧 `batch` 兼容仍在。
- 节点级 batch 的 `range` 只运行目标切片,并保持输出聚合顺序。
- 节点级 loop accumulate 的串行性:后轮能读到前轮累积值,最终写回 `accumulate.var`。
- append、extend、merge、replace 至少各有一个行为断言;断言契约结果,不要锁死内部 helper 名。
- `io.inputs` 缺 `item_var` 或 `accumulate.var` 时编译期 fatal,并使用 iterate 错误码。
- `iterate.over` 非 list 时 fatal,并使用 iterate 错误码。
- 图级 batch/loop 不能被“对外多次调用 graph.invoke”冒充。RED 至少要能区分单次 graph invoke 内部完成图级迭代,还是测试自己循环调用。
- 与 Step3 的 LOGIC 纯返回契约联动:loop 体里的 action 仍收到 plain dict,不重新引入 Context mutation 写回。
- 旧 MVP0 测试若断言 action 手写循环、run_skill 代替 iterate、或只认旧 `batch` 字段,必须改成 MVP1 RED 或删除。

## 7. 硬依赖约束

- 依赖 WS-E1 Step3:LOGIC action 纯返回已落地,Step4 不重新打开 Context mutation 通道。
- Step4 先于 WS-E1 Step5:Step5 子图 inputs 放宽会复用 graph exec/state slicing,但不应与 iterate 同时改 `graph_assembler.py`。
- Step4 不等待 WS-E5 的 checkpoint delta/compaction;但图级 loop=B 的轮次归属契约不能与未来 WS-E5 冲突。

## 8. 验收标准

- [ ] 已批准 RED suite 先失败,失败形状落在 `iterate` schema/runtime 缺口,不是夹具或环境问题。
- [ ] RED 通过契约门后,才允许写实施 task/Gemini prompt。
- [ ] 实现后 RED suite 变绿。
- [ ] Step3 LOGIC 契约套件保持绿。
- [ ] 旧 `batch` 行为保持兼容,但 MVP1 `iterate` 是主契约。
- [ ] 没有触碰 forbidden files。
- [ ] `uv.lock` 如被 `uv run` 摸脏,必须恢复,除非依赖变更属于本 WS scope 并已说明。
- [ ] 实现落地后回写 iterate 与 graph-exec baseline,照真实代码写。

## 9. 不做

- 不做真实 trace event emit 接线,不改 callbacks/events 或 callbacks/emit。
- 不做 checkpoint delta/compaction,不改 checkpointer/state。
- 不做子图 inputs 放宽,不改 loader 的 subgraph IO 校验;那是 Step5。
- 不做文件 lazy import 或 artifact business_data_md;那是 WS-E1-io。
- 不做 Studio 或 gateway。
- 不修无关 ruff 历史债。

## 10. baseline 回写指令

实现落地后按真实代码回写:

- `docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/baseline.md`:记录统一 `iterate`、节点级 loop、range、图级 batch/loop 的真实落地状态。
- `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md`:记录声明式循环对 LOGIC/action 编排边界的影响。
- 如 manifest/loader 语法落地,同步 `docs/engine/mvp1/01-contract/02-skill-syntax/baseline.md`。
- 如新增 iterate 错误码进入注册表,同步 `docs/engine/mvp1/01-contract/03-compile-rules/baseline.md`。

## 11. 评审检查点

- 契约门:审 RED 是否忠实编码 MVP1 iterate 目标,是否避免把旧 `batch` 或测试自循环当成图级 iterate 假绿。
- Codex 审查退出:以 §8 全满足为准。
- Claude 终审:查 baseline 是否诚实、测试是否过锁、是否误碰 E2/E5/E1-io/Studio/gateway。

## 12. 给 Codex 的交接

契约门通过后,再据已批准 RED 写 `.kiro/specs/engine-mvp1/task-ws-e1-step4-iterate-runtime.md` 和 Gemini prompt。task/prompt 必须包含工作区路径、必读文件、RED 失败结果、owns_files、禁止触碰、验证命令和回报格式。禁止在 RED 未过契约门前写 task 或实现。
