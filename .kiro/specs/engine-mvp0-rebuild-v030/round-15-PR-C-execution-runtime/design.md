# PR C 组 (execution-runtime) 架构设计

本文档基于 a1↔a2 cross-audit 后收敛的定稿 (`/tmp/pr-c-converged-design.md`) 编写，用于指导 C 组 (execution-runtime) 的开发和实现。

## 1. 现状审计表

| 任务 | 状态 | 证据 (file:line) |
|---|---|---|
| C1 退役 exit_contract | **未做** | `runtime/exit_contract.py:8` 仍是 V2.1 `inject_exit_contract` 每轮追加 HumanMessage |
| C2 cognitive 8 插槽 | **需重做** | `cognitive/prompt.py` `apply_v030_cognitive_template` 有独立 `<steps>:196` / `<examples>:200` 脱壳壳, knowledge_base 仅 `{knowledge_base or "无预读取参考资料"}`, 偏离 §5 |
| C3 SkillResolver DI | **已做 merge** | `compiler.py` 等 29 处已注入 (δ) |
| C4 reference reader | **部分 scaffold** | `core/builtin_subagents/reference_reader.py` 仅 `ReferenceReaderRuntime` 沙盒类 (30 行), 无装配期调用/timeout/fallback |
| C5 read_reference/read_example tools | **未做** | `tools/builtin/` 无这两文件 |
| C6 subagent/SUBGRAPH resolver | **部分 scaffold** | `graph_assembler.py` 已接 skill_resolver; 缺口是 child flow 不深拷贝: subagent 用 `parent_state.get("flow",{})` 直接传 (`graph_assembler.py:617-623`)，且 SUBGRAPH 路径 `_subgraph_node` 在 `graph_assembler.py:239` 用 `dict(state.get('flow',{}))` 浅拷贝同样不满足 D4 deepcopy |
| C7 ActionRegistry 一级寻址校验 | **未做** | `core/actions.py:23` 只有 `_by_phase` resolve (84 行), 缺 `/`,`.`,`..`,绝对路径防逃逸 |
| C8 e2e | **未做** | 缺 V0.3.0 reference reader fallback / builtin tools / SUBGRAPH 覆盖 |
| D4 subagent resolver/深拷贝 | **未做** | child flow deep copy + depth 未做 (`tasks.md:421-428`) |

## 2. PR 拆分 (1 个统一 PR，内部 3 Commit)

为保证 Hard cutover 原子落地，避免主干半坏状态，C 组任务合并为 1 个 PR 进行。

- **Commit 1 (C1 + C2)**:
  - 物理删 `exit_contract`。
  - cognitive 8 插槽严格对齐 §5。
- **Commit 2 (C4 + C5 + C7)**:
  - reader 装配期降级处理。
  - builtin tools 注入，并修复 C5 运行期 not-found 错误码。
  - Action 沙盒拦截，以及 C7 返回多余字段 FATAL 策略。
- **Commit 3 (C6 + D4 + C8)**:
  - resolver subgraph runtime 接轨。
  - child flow 深拷贝。
  - e2e 测试与 resolver fixture 统一大迁移。

## 3. 架构设计 (逐 task)

### C1 ExitContract 退役
- 彻底删除 `runtime/exit_contract.py`，清理 `graph_assembler.py` 与所有 tests 对 `inject_exit_contract` 的依赖调用。
- 将 `<exit_contract>` XML 文本 hardcode 写死在 `prompt.py` 中 system template 的末尾，内部拼接 `{output_schema}`。**不**作为 HumanMessage 每轮附带。

### C2 Cognitive 8 插槽 (严格按 ground truth §5)
废弃现有的独立 `<steps>` 和 `<examples>` 脱壳层。
8 个固定容器与精确占位符命名：
1. **`<role>`**: `{skill_role}` + `{llm_role_prefix_section}` (可选)
2. **`<goal>`**: `{skill_goal}`
3. **`<thinking_style>`**: 静态策略提示 + 包含 "建议步骤:" 的 `{skill_steps_splat}`（即 body `<step>` 原样平铺，不脱壳）。
4. **`<knowledge_base>`**: 使用 `{aligned_concepts_and_critical_corrections_markdown}` (装配期输出，不是 `{reference_reader_subagent_output_markdown}`)，并附加调用工具的提示和 `{reference_registry_listing}`。
5. **`<examples>`**: 内联 `{skill_examples_inline}` 与扩展库 `{example_registry_listing}`。
6. **`<ambiguity_feedback>`**: 硬编码防静默跳过文案。
7. **`<protocol_citation>`**: 硬编码引用要求，附 `{skill_protocols_splat}`。
8. **`<critical_reminders>`**: 硬编码检查逻辑。
- 尾部：`<exit_contract>` 内嵌 `{output_schema}`。

### C4 Reference Reader 装配期 Flow + Fallback
- **触发点**：在 `graph_assembler._build_skill_node()` (`graph_assembler.py:259-317`) 构建 Agent node **前**触发一次。不可以在 `_skill_node()` 中每轮触发。
- **契约输入**：`skill_id`, `phase_id`, `references`, `max_output_tokens`, `language` (需扩展 `ReaderSandboxState`)。
- **Fallback 机制**：必须有真实的 60s timeout wrapper。超时或异常时，不阻断 Agent，截取前 3000 tokens，附加上警告信息并抛出 WARN 码 `[F-v3-reference-reader-failed]` 降级。
- **与 Fatal 区别**：运行时异常降级；而在 Compile 期间如 reference path 非法则抛出 `[F-v3-resource-reference-path-invalid]` FATAL。

### C5 read_reference / read_example builtin tools
- 在 `tools/builtin/` 下新建 `read_reference.py` 和 `read_example.py`。
- 接收 `id` 参数。仅允许访问当前 phase manifest 的 registry。跨 skill/path 逃逸一律短路拦截不读取文件。
- **未声明 ID 错误码**：
  - `read_reference` → `[F-v3-resource-reference-not-found]`
  - `read_example` → `[F-v3-resource-example-not-found]`
  - (不是 mention-target-not-found)。

### C7 ActionRegistry 一级寻址校验
- 正则拦截：按编译期校验定性（name 在 LOGIC.md 编译期固定，runtime resolve 理论不触发）。拦截所有带 `/`, `\`, `..`, `.`, 绝对路径和 module path 的 action name 请求，抛出 **FATAL `[F-v3-logic-action-name-invalid]`**。
- 寻址范围：限定在 `phases/<phase_id>/actions/<name>.py` 或是全局 Common action registry 中。
- **多余字段校验**：错误码重命名为 `[F-v3-logic-output-field-undeclared]` + 补 ctx 突变路径校验。当前 `result` 已有 Fatal 拦截，但 `ctx.data` 突变路径（如 `:210` 旁路）绕过了校验，需针对此缺口进行补漏。设计决策（G2）：一旦发现未声明字段的写入（不论是通过 action dict return 还是 ctx.set 就地突变），**统一抛出 FATAL `[F-v3-logic-output-field-undeclared]` 终止，不交给 StateMapper 拦截**。

### C6 + D4 subagent/SUBGRAPH resolver 与 深拷贝
- **C6**: 全面走 `target_skill` resolver 加载。不提供 `child_graph_path` public tool 参数。
- **D4**: 深拷贝隔离 `flow`。`parent_state.get("flow", {})` 必须 deep copy，并自增 `subagent_depth`，防止父级数据泄漏污染子图环境。

### C8 e2e 测试点
- Minimal Agent run 结合完整的 cognitive template（校验 `{aligned_concepts...}` 不为空）。
- Reference Reader 超时/异常 mock 触发 fallback，将 `[F-v3-reference-reader-failed]` markdown 注入 system prompt。
- 验证 `read_example` 和 `read_reference` 的 runtime 合法调用。
- SUBGRAPH target_skill 全链路执行及子状态防泄漏断言。

## 4. [BREAKING]/[NEW] 继承字段表

V0.3.0 为 Hard cutover，不提供向下兼容处理，仅提供标记以明确设计意图：

| 字段/规范 | 类型 | 说明与迁移路径 |
|---|---|---|
| `schema_version` | **[BREAKING]** | 强制验证 `"v0.3.0"` |
| `mode` (YAML frontmatter) | **[BREAKING]** | 删除该字段配置。改由 loader 从 `SKILL.md` 等物理文件名推断。 |
| `<exit_contract>` | **[BREAKING]** | 物理删除 `inject_exit_contract`，引擎硬编码入 Prompt。 |
| `path` (子图与子Agent路径) | **[BREAKING]** | 废弃路径引用，统一切换为基于 `target_skill` 的寻址。 |
| `validator` | **[NEW]** | 各 Phase 文件新增布尔字段，默认为 false。 |

> 注：依据保守原则，未在此表列出的现有字段或约定，默认继承不做变动。

## 5. 高风险碰撞防范
1. **Prompt Snapshot 脆弱**：由于 C1/C2 会彻底改变 prompt 结构，原测试需将断言由全量匹配改为关键子字符串（slot substring）校验。
2. **Compile Skill Cache**：加入 resolver 后，原 `skill_id` 下可能有不同的 sub-graph 配置，导致 cache namespace 污染。须配合 bump namespace version。
3. **Fixture DI**：原有的大量使用 `compile_skill` 的 tests，需要提供 `skill_resolver` 参数，不可依靠默认空值跳过 C3 拦截。
