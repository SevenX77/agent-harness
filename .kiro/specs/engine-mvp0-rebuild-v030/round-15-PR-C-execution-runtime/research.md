# PR C 组 (execution-runtime) 调研报告

本文档基于对现有代码库的真实状态进行核查与梳理，以便 PR C 组明确目前代码的基础点及下一步改造切入点。

## 1. 代码库现状清单 (基于 a1+a2 grep 与 verify)

### 已 Merge (包含但不限于)
- **C3 (SkillResolver DI)**: 已在 `compiler.py`、`runner.py`、`graph_assembler.py` 内部全面通过依赖注入，涉及 29 处代码更改。(δ 版本完成)
- **D1 (Inline IO 处理)**: `state_mapper.py:24-62` 中实现了 `filter_runtime_inputs` / `build_phase_input` / `wrap_phase_output` 处理运行时的 Inline IO 参数对接。
- **D3 (沙盒类基础定义)**: `state_mapper.py:159` 中存在 `ReaderSandboxState` 类，为 builtin reference reader 的黑板沙盒。

### 部分 Scaffold / 未完成主干逻辑
- **C4 (Reference Reader)**: 在 `core/builtin_subagents/reference_reader.py` (30行代码) 中仅定义了一个包含基础状态包裹的 `ReferenceReaderRuntime`，但核心的 `_build_skill_node` 装配调用逻辑、60秒 timeout 设置和发生错误时的 fallback 降级等皆为空白。
- **C6 (Subagent / SUBGRAPH Resolver)**: 在 `graph_assembler.py` (如 617-623 行) 虽然已经通过 `skill_resolver` 获得子阶段资源，但在生成子状态 `child_flow` 时，直接传递了 `parent_state.get("flow", {})` 的引用，没有做 `deep copy` 和 `depth` 处理 (D4 漏斗泄漏问题)。

### 完全未做
- **C1 (ExitContract 废弃)**: 文件 `runtime/exit_contract.py:8` 中的 `inject_exit_contract` 代码仍然存在，被当做每轮的 HumanMessage 附带执行。
- **C2 (Cognitive 8 插槽偏离)**: `cognitive/prompt.py` 中 `apply_v030_cognitive_template` 函数仍然拥有非规范的 `<steps>:196` 和 `<examples>:200` 包裹标签，同时 `knowledge_base` 只是个极其简陋的默认值，没有 8 插槽的结构规范。
- **C5 (Resource Tools)**: `tools/builtin/` 下只有 `parallel_map`, `read_file` 等，未建立 `read_reference.py` 与 `read_example.py`。
- **C7 (Action 目录隔离/输出拦截)**: `core/actions.py:23` 仅包含基础的按 Phase 获取的 `_by_phase` Map 字典，缺乏跨目录探测（`/`, `.`, `..`）的防逃逸正则拦截。
- **C8 (e2e 覆盖)**: 没有任何测试覆盖 v0.3.0 e2e 的 `[F-v3-reference-reader-failed]` 降级场景。

## 2. 规范基准

### Ground Truth §5 与 错误码约束
根据 `docs/engine/mvp0/skill-spec/00-FORMAT-GROUND-TRUTH.md` 与 `11-error-code-spec.md`:
1. `{aligned_concepts_and_critical_corrections_markdown}` 是唯一合法的装载期 Reference Reader 降级填入变量。
2. 内部的 thinking style 等插槽包含的内容**不允许带有外壳**（如无 `<steps>` 脱壳操作，需直接使用 `{skill_steps_splat}` 平铺）。
3. Resource Runtime Tool 的 not found 错误码：
   - reference 对应 `[F-v3-resource-reference-not-found]` (运行期)。
   - example 对应 `[F-v3-resource-example-not-found]` (运行期)。
4. `[F-v3-logic-output-field-undeclared]` 为 C7 (Action) 的多余字段 Fatal 错误码。

### 09-builtin-modules-spec 约束摘录
Reference Reader 需要接受的参数有：`skill_id`, `phase_id`, `references`, `max_output_tokens`, `language`。因此现有的 `ReaderSandboxState` 需要被扩展。

## 3. 装配层与 API 现有结构分析

### _build_skill_node vs _skill_node 机制
- `_build_skill_node` (`graph_assembler.py:259-317`) 是节点对象**创建期间**执行的编译上下文层。
- `_skill_node` (`graph_assembler.py:327-329`) 是每个大模型循环周期内 **invoke 调用时**所触发的执行闭包。
- **结论**：C4 要求装配期执行一次 reference 读取任务，必须将其闭包挂在 `_build_skill_node` 的上下文执行期，这样才能计算出 `knowledge_base_markdown`，而不被每轮重复触发。

### D1/D3 现状 API 与 Cache Key
- **D1 API**: 当前的 `StateMapper.build_phase_input` 和 `wrap_phase_output` 已使用 `filter_runtime_inputs` 约束输入层。但在 C7 对于 Action 节点的输出侧，它通过 `updates.update(result)` 回写 (`graph_assembler.py:203-213`) 时，`result` 已经过 `_validate_logic_update_keys` 校验抛出 Fatal。真实缺口是 ctx 突变路径 `:210` 旁路未校验：即 `updates.update(_dict_delta(before, data))` 把 action 对 `ctx.data` 的就地突变直接写进 updates，未受多余字段拦截约束。
- **Cache Key**: 在 `compiler.py:57-65` 中，当前的 Cache Key 只认 `skill root`。当引入 C3/C6 也就是 Skill Resolver 之后，不同运行时环境或 Resolver 实现给出的 root 一样但内部 sub-registry 可能变化，必须提升 cache key 生成的敏感度，将 registry / resolver 身份一并纳入。
