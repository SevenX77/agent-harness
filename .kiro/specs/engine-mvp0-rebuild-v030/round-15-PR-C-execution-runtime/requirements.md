# PR C 组 (execution-runtime) 需求 (验收标准)

本文档将收敛设计转化成可执行的 Acceptance Criteria，作为 PR 提交测试先行（Tests-First 红灯 suite）与最终交付审核的基准。

## 1. C1 / C2：Cognitive 8 插槽与结构断言
**前置条件**：完全物理移除 `runtime/exit_contract.py`，不再随 Agent History Message 追加。
**验收条件**：
- [ ] 测试运行后生成的 System Prompt 必须存在 `<role>`, `<goal>`, `<thinking_style>`, `<knowledge_base>`, `<examples>`, `<ambiguity_feedback>`, `<protocol_citation>`, `<critical_reminders>` 这 8 个固定的 XML 容器标签。
- [ ] 模板内不能出现独立的 `<steps>` 和 `<document_examples>` 复数脱壳包外壳标签。
- [ ] SKILL.md body 中定义的 `<step>` 内容必须原样平铺在 `{skill_steps_splat}` 所属的 `<thinking_style>` 中。
- [ ] 末尾必须以 `<exit_contract>` 结束，并内嵌 `{output_schema}` 提供 JSON Schema 的 Markdown 转换文本。
- [ ] 覆盖测试：`tests/cognitive/test_v030_cognitive_template_slots.py`。

## 2. C4 / D3：Reference Reader 装配期触发与 Fallback 降级
**前置条件**：扩展 `ReaderSandboxState`，提供 `references`, `max_output_tokens`, `language` 等支持。
**验收条件**：
- [ ] Agent 执行装配时（`_build_skill_node`），`ReferenceReaderRuntime` 必须被且只被触发一次。
- [ ] Reader 必须有强制的 60s timeout 上下文包裹。
- [ ] Mock 网络超时或非法输出格式（LLM 解析错误等），系统不能 Crash 阻断 Agent 的启动流程。
- [ ] 当发生 Fallback 降级时，输出为前 3000 Token 截断的原始文档，并在前面附加警告文本：产生 `[F-v3-reference-reader-failed]` 相关的错误内容，并注入到 `{aligned_concepts_and_critical_corrections_markdown}` 中。
- [ ] 覆盖测试：`tests/core/test_reference_reader_assembly_fallback.py`。

## 3. C5：Builtin Resource Tools (read_reference, read_example) 运行期
**验收条件**：
- [ ] 注入 `read_reference` 与 `read_example` tool。
- [ ] 对于传入未在 phase manifest registry 声明的 `id` 请求，执行路径不触发真实 File IO，直接立即短路返回。
- [ ] 未声明 ID 分别报错：
  - `read_reference` 抛出/返回 `[F-v3-resource-reference-not-found]`。
  - `read_example` 抛出/返回 `[F-v3-resource-example-not-found]`。
- [ ] 任意利用工具参数尝试获取其他目录或 skill root 逃逸的数据都被强制拦截并抛错。
- [ ] 覆盖测试：`tests/tools/test_builtin_resource_tools.py`。

## 4. C7：ActionRegistry 一级沙盒拦截与多余字段校验
**验收条件**：
- [ ] `ActionRegistry` 必须按编译期校验定性（name 在 LOGIC.md 编译期固定）。通过正则表达式主动拦截 `name` 中的 `/`, `.`, `..` 及绝对路径，拦截到非法字符直接抛出 FATAL `[F-v3-logic-action-name-invalid]`。
- [ ] 运行时接收到 Action 执行的 Dict 结果或对 ctx 的就地突变后，引擎会针对 `LOGIC.md` `io.outputs` 字段进行比对。
- [ ] 当发现未被声明的多余返回字段时（无论来自字典返回还是 ctx.set 突变），程序统一抛出 **FATAL** `[F-v3-logic-output-field-undeclared]`，**抛错不截断**，中断当前 phase 状态回写闭环。
- [ ] 覆盖测试：`tests/core/test_action_registry_v030.py`。

## 5. C6 / D4：Resolver 寻址与 Subagent 隔离泄漏
**验收条件**：
- [ ] 所有通过 `subagent` 与 `SUBGRAPH` 发起的图内部调用，必须从 `skill_resolver` 调用 `resolve_skill(target_skill)` 建立。
- [ ] 构建子集状态 `child_flow` 时，父级的 `flow` 属性字典必须由深拷贝 (`deepcopy`) 产生。
- [ ] 必须递增 `subagent_depth` 值。
- [ ] 父子状态的黑板信息互不污染。测试需要包含故意在子节点篡改 `flow`，然后断言回到父节点时父 `flow` 未受破坏的场景。
- [ ] 覆盖测试：包含在 e2e 覆盖范围以及 `tests/runtime/` 层级中。

## 6. C8：V0.3.0 E2E 覆盖
**验收条件**：
- [ ] 新增 `tests/e2e/test_execution_runtime_v030.py` e2e 测试集。
- [ ] 完整的 Minimal Agent Run，结合 C2 的 Cognitive 模版解析 `{aligned_concepts_...}` 和 `{skill_steps_splat}` 不为空。
- [ ] 覆盖一次 `read_example` 的合法调用。
- [ ] 验证 SUBGRAPH 通过 `target_skill` 跑通整图执行的 `business_data_md` 返回和结构化映射。
`target_skill` 跑通整图执行的 `business_data_md` 返回和结构化映射。
