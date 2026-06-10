---
ws_id: WS-E1-io-runtime
modules:
  - 11-io
  - 02-mechanism/04-run-outer/01-graph-exec
  - 02-mechanism/06-seam/02-observability
  - 01-contract/02-skill-syntax
  - 01-contract/03-compile-rules
depends_on:
  - WS-E1-step5-subgraph-io
  - WS-E4-v4-trace-events
  - WS-E5-checkpoint-inner
blocks: []
owns_files:
  - .kiro/specs/engine-mvp1/requirements-ws-e1-io-runtime.md
  - packages/graph-agent/tests/core/test_ws_e1_io_runtime_red.py
  - packages/graph-agent/tests/e2e/test_ws_e1_io_runtime.py
  - packages/graph-agent/src/graph_agent/core/graph_assembler.py
  - packages/graph-agent/src/graph_agent/tools/builtin/read_file.py
  - packages/graph-agent/src/graph_agent/io/manager.py
  - packages/graph-agent/src/graph_agent/io/storage.py
  - packages/graph-agent/src/graph_agent/core/runner.py
spec_ssot:
  - docs/development/task-spec-standard.md
  - docs/engine/mvp1/_impl/IMPL_PLAN.md
  - docs/engine/mvp1/_impl-backlog.md
  - docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md
  - docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md
  - docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md
  - docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md
  - docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md
status: implemented-review-pending
created: 2026-06-10
baseline_head: 34ee40f1b8e51d6d2d5fc413e227d630b4aa9c5e
review_flow: requirements -> RED -> contract gate -> task + Gemini prompt -> Gemini GREEN -> Codex hard-exit review -> baseline writeback -> final review
process_note: 2026-06-10 contract gate overrun was detected after production diff already existed and WS tests were GREEN; user approved no rollback, so this work is being audited as implementation-review remediation rather than normal post-gate implementation.
---

# WS-E1-io Runtime IO - 需求书

> 本需求书原本是 WS-E1-io 的流水线输入：下一步应只写 RED 测试并跑到干净失败；未见 RED、未过契约门，不得写实施 task/Gemini prompt，不得实现生产代码。实际执行中发现 worktree 已越过契约门且生产 diff 已存在，用户确认不回滚，改按实现审查补救；因此后续状态以实现审查报告、baseline 回写和终审为准。

## 1. 目标

补齐 WS-E1 Step5 之后拆出的 11-io 运行时能力：节点声明文件导入时，外部文本文件必须在目标节点真正运行前才 lazy 注入黑板字段，并继续走普通 StateMapper `io.inputs` 切片；`io.outputs` 的 file/artifact 路径标注必须写入通用 engine workspace/run artifact 位置；markdown artifact 必须优先使用已通过校验的原始 `business_data_md`，不能从 parsed JSON 再回转成 markdown。

## 2. SSOT 指针

- 流程标准：`docs/development/task-spec-standard.md` §一/§三/§四。requirements 只写契约、边界、测试要求；契约门前不写 task/Gemini prompt。
- 实施计划：`docs/engine/mvp1/_impl/IMPL_PLAN.md` §二/§三/§四/§七，WS-E1-io 依赖 WS-E1/E4/E5 后接入。
- backlog 来源：`docs/engine/mvp1/_impl-backlog.md` Tier 2 I5。
- 目标唯一真理：`docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md` §2/§5 的 E2/E3。
- 原始现状起点(需求书创建时)：`docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md` §6 和差异表，文件导入无机制，md artifact 尚未接 `business_data_md`。
- 原始事件现状(需求书创建时)：`docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md` §1/§4，`InputFileInjectedEvent` schema 已存在，真实 emit 尚未接。只能复用既有 schema，不能扩 schema。
- 语法目标：`docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md` §2.10.1-§2.10.4。声明必须是 engine 通用 io 语义，不含 Studio 产物或 UI 字段。
- 编译/运行错误背景：`docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md` §2.3、runtime/state mapping 错误码、tool/agent 相关错误码。
- 必读源码：
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`：`_wrap_phase_runtime_node`、`_build_logic_node`、`_build_skill_node`。
  - `packages/graph-agent/src/graph_agent/tools/builtin/read_file.py`：现有文本读取、路径限制、错误包装语义。
  - `packages/graph-agent/src/graph_agent/io/manager.py`：`IOManager.save_outputs`、file/artifact target 分发。
  - `packages/graph-agent/src/graph_agent/io/storage.py`：`StorageManager.save_artifact`、`ArtifactSavedEvent`。
  - `packages/graph-agent/src/graph_agent/core/runner.py`：`run_skill`/`_run_v030_skill_dict` 的 `workspace_dir`、run dir、declared output 保存路径。
  - 只读 grounding：`packages/graph-agent/src/graph_agent/core/state.py` 的 `StateManager.update_business` / `FrameworkState.finish_task_result`，`packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py` 的 `business_data_md` 保留路径。

## 3. 文件归属

本 WS owns 见 frontmatter `owns_files`。

- `graph_assembler.py` 是文件 lazy 注入的运行时落点，但只允许处理节点进入前的通用 io 注入与已有事件 emit；不得重开 create_agent、subgraph IO、iterate、checkpoint、exit gate。
- `read_file.py` 只允许沉淀可复用的通用文本读取/路径边界行为；不得把 reference-only 工具语义直接泄漏成 runtime 注入错误语义。
- `io/manager.py` 与 `io/storage.py` 只允许处理 declared `io.outputs` file/artifact 保存、filename/path 规则和 markdown 原文选择；不得引入 Studio 下载/预览概念。
- `runner.py` 只允许把 engine `workspace_dir` / run artifact dir / final state 或 finish metadata 接入 declared output 保存；不得实现 resume/golden 或 Studio HTTP。
- `core/state.py` 与 `middleware/cognitive_flow.py` 当前不纳入 owns：代码现状已能把 `business_data_md` 存入 `FrameworkState.finish_task_result`。如果 RED/GREEN 证明该现状不足以可靠接线，必须先停下请求扩 scope，并在 requirements/task 中解释原因。

禁止触碰：

- `packages/graph-agent/src/graph_agent/callbacks/events.py` / `callbacks/emit.py`：事件 schema/emit helper 归 WS-E4 或既有 schema 工作，本 WS 只复用。
- `apps/studio/**`：Studio 只是 consumer，本 WS 不做 UI/HTTP/下载预览。
- `packages/graph-agent-gateway/**`。
- `packages/graph-agent/src/graph_agent/core/checkpointer.py`、checkpoint 语义、resume/golden。
- `packages/graph-agent/src/graph_agent/middleware/nudge_injector.py`、exit gate、middleware tail slots。
- `packages/graph-agent/src/graph_agent/core/loader.py` 的子图 IO 放宽规则，WS-E1 Step5 已完成。

## 4. 现状锚点

当前 V0.3 runner 只把根输出 schema 中 `target: file` 的字段通过 `IOManager.save_outputs` 写到 run artifacts 目录；`target: artifact` 不在 `_save_v030_declared_file_outputs` 中保存。节点 `io.inputs` 里的文件导入声明没有 runtime 机制，`_wrap_phase_runtime_node` 直接让 StateMapper 从现有 blackboard 切片。AGENT finish_task 路径会把 parsed business data hoist 到 business data，同时在 `FrameworkState.finish_task_result` 里保留原始 `business_data_md`，但 declared artifact 保存还没有优先取这份原文。

## 5. 目标行为

### 5.1 文件导入到黑板必须 runtime lazy

- 节点 `io.inputs.properties.<field>` 可以声明该字段来自 workspace 内的文本文件。声明必须是 JSON-Schema-compatible 的 engine 通用注解，不能依赖 Studio 路径、DTO 或 UI 字段。
- 文件只在目标节点实际运行前读取。图启动、无关节点执行、上游失败阻断目标节点时，不得提前读目标节点声明的文件。
- 读取成功后，字段写入 `WorkflowState.data` 的普通 business 字段；随后目标 phase 仍通过自己的 `io.inputs` 切片拿到父黑板字段和注入字段。phase action/agent/subgraph 不能拿到未声明字段。
- 注入字段必须遵守 `StateManager.update_business` 的 business/framework 边界；不得写 `_` 前缀框架字段，不得把文件句柄、Path 对象或 runtime manager 塞进 business data。

### 5.2 文件路径和错误行为

- 文件读取必须限制在通用 engine `workspace_dir` 和声明路径规则内。相对路径以 engine workspace/run 约定解析；绝对路径、`..` 越界、符号链接逃逸等不得读出边界。
- 文件导入只承诺文本策略。缺失文件、越界路径、目录而非文件、二进制/不可按声明文本编码读取等情况必须产生稳定 engine 错误结果，不能靠 Python traceback、裸 `KeyError` 或 reference tool 的字符串错误继续流入业务字段。
- 如果发 `InputFileInjectedEvent`，只能使用已有通用事件 schema；事件内容不能新增 Studio-only 字段，也不能扩 `callbacks/events.py`。

### 5.3 `io.outputs` file/artifact 保存

- `io.outputs.properties.<field>` 的 declared output 可以要求写成 file 或 artifact。保存位置必须在 engine `workspace_dir` 的 run-scoped artifact 位置或声明允许的 workspace 相对路径内；不得写 skill 源码树、当前进程 cwd 任意位置或 Studio 私有目录。
- filename-only/path-less 的 declared artifact 必须落到通用 run artifact 目录，并返回/记录可被 engine trace/result 消费的真实路径。
- path 模板只能解析当前 run context 中明确允许的 business/framework 字段；缺失占位符、越界路径或不合法文件名必须稳定失败。
- `StorageManager.save_artifact` 对 str/bytes 原样写、非 str JSON 序列化的既有语义可以继续作为底层能力，但输出路径规则和 runner 接线必须以本 WS 契约为准。

### 5.4 markdown artifact 使用原始 `business_data_md`

- 当 AGENT phase 的 validated `business_data_md` 对应 declared markdown artifact 时，artifact 内容必须优先使用原始 markdown 字符串。
- 不得用 `business_data_parsed` / parsed JSON / hoisted business data 再拼回 markdown。测试必须能证明注释、空行、顺序或其他 markdown 细节不会因 JSON 回转丢失。
- 如果没有可用的 validated `business_data_md`，实现必须稳定失败或按清晰声明的非-md 输出规则保存；不得静默写错误内容。

## 6. 测试要求

Codex 必须先写 RED，建议落点：

- `packages/graph-agent/tests/core/test_ws_e1_io_runtime_red.py`
- `packages/graph-agent/tests/e2e/test_ws_e1_io_runtime.py`

RED 必须覆盖：

- compile/runtime 层可以声明“文件导入 -> 目标字段”，并且目标节点运行时该字段与父黑板已有字段一起按本节点 `io.inputs` 被切片，phase 跑通并输出。
- 文件导入是 lazy 的：上游失败阻断目标节点时，不得读目标节点声明的缺失/越界文件，也不得发 `InputFileInjectedEvent`。
- 文件不存在、越界路径、目录/非文本/二进制策略至少各有稳定错误行为测试；失败信息不得暴露 Python traceback，也不得把 read_file 字符串错误当业务输入继续执行。
- `io.outputs` artifact/file 保存到通用 workspace/run artifact 位置，支持 filename/path 规则，不写 skill 源码树或 Studio 私有目录。
- markdown artifact 使用原始 `business_data_md`；测试必须构造 parsed data 无法保留的 markdown 细节，证明最终文件内容来自原文。
- 至少一条真实 run/e2e 走 `run_skill` 或等价 public engine path，不只测 helper。
- 回归不破：WS-E1 Step3/Step4/Step5、WS-E2、WS-E5、WS-E8 的核心测试仍应纳入后续 GREEN 验证计划。RED 阶段先跑本 WS 新测试并记录失败形状。

## 7. 硬依赖约束

- 依赖 WS-E1 Step5 已放宽子图 inputs，WS-E4 已提供 `InputFileInjectedEvent` schema，WS-E5 已提供 `StateManager.update_business` 和 finish metadata 边界。
- 本 WS 先写 requirements，再写 RED，再停在契约门。RED 失败形状应落在缺少文件 lazy 注入、declared artifact 保存或 `business_data_md` 接线，而不是夹具、resolver 或环境问题。
- 契约门通过后，才允许写 `.kiro/specs/engine-mvp1/task-ws-e1-io-runtime.md` 和 Gemini prompt。
- 如果现有 skill syntax/AST 不能表达通用文件导入或 artifact 路径标注，Codex 必须在 RED/契约门报告，不得发明 Studio-only 语法绕过。

## 8. 验收标准

- [ ] worktree、分支、base commit 已核实，工作区起点 clean。
- [ ] requirements 写完后才写 RED；契约门前不写 task/Gemini prompt。
- [ ] RED 测试先失败，且失败形状忠实指向 E2/E3 缺口。
- [ ] 文件导入只在目标节点运行前 lazy 读取；上游失败/未到达目标时不提前读。
- [ ] 注入字段写入普通 business data，并由目标 phase 自己的 `io.inputs` 切片消费。
- [ ] 缺失、越界、目录/二进制/非文本输入都有稳定 engine 错误行为。
- [ ] declared file/artifact 输出只写 engine workspace/run artifact 位置或合法声明路径。
- [ ] markdown artifact 使用 validated `business_data_md` 原文，不从 parsed data 回转。
- [ ] 至少一条真实 run/e2e 通过。
- [ ] 未扩事件 schema，未触碰 Studio/gateway/resume/golden/exit gate。
- [ ] 实现落地后 baseline 按真实代码回写。

## 9. 不做

- 不做 Studio UI、HTTP、下载/预览 DTO。
- 不做 callbacks/events.py 或 callbacks/emit.py schema 改动。
- 不做 runner resume、checkpoint 语义、golden eval。
- 不做 middleware tail slots、exit gate、nudge、V4 runtime edge events 泛化收口。
- 不重开子图 IO Step5，不改 loader 的 subgraph outputs 严校。
- 不把 artifact 实体、golden 实体或 Studio 产物写进 skill syntax。

## 10. baseline 回写指令

实现落地后按真实代码回写：

- `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md`：记录文件 lazy 注入、StateMapper 切片接线、`io.outputs` file/artifact 真实路径规则、`business_data_md` 原文接线；仍未完成的 required 校验/trace 深集成照实保留。
- `docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md`：如果本 WS 接入了 `InputFileInjectedEvent` runtime emit，只记录真实发射点；未接则诚实保留缺口。
- `docs/engine/mvp1/_impl/IMPL_PLAN.md`：如 PM 要求维护进度面板，更新 WS-E1-io 状态。

## 11. 评审检查点

- 契约门：重点审 RED 是否忠实覆盖 lazy 文件注入、workspace 路径边界、declared artifact 路径、`business_data_md` 原文，以及是否越界到 Studio/events schema/resume/golden。
- Codex 审查退出：以 §8 全满足为准；必须看真实 run/e2e 和实际文件内容，不接受只 mock helper 到绿。
- Claude 终审：查实现是否 engine-first、baseline 是否诚实、测试是否非假绿、forbidden files 是否未触碰。

## 12. 给 Codex 的交接

契约门通过后，Codex 据已批准 RED 写 `.kiro/specs/engine-mvp1/task-ws-e1-io-runtime.md` 和 Gemini prompt，遵守：

- 来源 = 已批准测试，测试是契约；不凭空设计实现步骤。
- 格式 = Phase 分段 + `- [ ]` 勾选项 + 每条挂 `_Requirements: <模块.功能>` + 验证命令。
- frontmatter 指回本需求书和 `spec_ssot`，不重写设计。
- 嵌入编排注解：`owns_files`、实现者 = Gemini、§8 硬退出。
- 行号 Codex 落地时自己重新核；本需求书不把行号当编辑坐标。
- 不跑 `/kiro:spec-tasks`，避免 clobber。
- 同步输出 Gemini prompt，包含工作区路径、必读文件、RED 测试结果、owns_files/禁止触碰、目标行为、验证命令和回报格式。
