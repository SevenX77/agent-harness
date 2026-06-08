---
module: 01-contract/02-skill-syntax
doc: baseline
status: drafted（现状对齐 WS-E1 Step4 后代码；GRAPH/LOGIC/SUBGRAPH/AGENT/cognitive/mention 解析已核实；统一 `iterate` 语法已 live;LOGIC runtime 已纯返回,但 action 签名命名、SUBGRAPH path/io、AGENT/cognitive/mention 严格契约仍有 refactor-target drift）
binds_alignment: ./mvp1-alignment.md
binds_code: packages/graph-agent/src/graph_agent/core/loader.py:SkillLoader.compile_skill; packages/graph-agent/src/graph_agent/core/loader.py:_parse_agent_body; packages/graph-agent/src/graph_agent/core/loader.py:_validate_agent_mentions; packages/graph-agent/src/graph_agent/core/loader.py:_validate_iterate_compile_contracts; packages/graph-agent/src/graph_agent/core/manifest.py:GraphManifest; packages/graph-agent/src/graph_agent/core/manifest.py:IterateSpec; packages/graph-agent/src/graph_agent/core/manifest.py:LogicNodeAST; packages/graph-agent/src/graph_agent/core/manifest.py:SubgraphNodeAST; packages/graph-agent/src/graph_agent/core/manifest.py:AgentNodeAST; packages/graph-agent/src/graph_agent/core/mentions.py:scan_mentions; packages/graph-agent/src/graph_agent/cognitive/prompt.py:apply_v030_cognitive_template; packages/graph-agent/src/graph_agent/core/graph_assembler.py:_agent_system_prompt
---

# 02-skill-syntax — Baseline(当下代码实现逻辑)

> **Scope**: skill 文件语法的**当前代码现状**:GRAPH/LOGIC/SUBGRAPH/AGENT 的 frontmatter 解析、body 解析、AST、mention 扫描与 cognitive prompt 模板装配入口。本文只对照代码,不拿旧 spec 当现状。
> **现状一句话**:当前代码已能解析 V0.3.0 `GRAPH.md`、`LOGIC.md`、`SUBGRAPH.md`、Agent `SKILL.md`,并有 `core/mentions.py` 与 `apply_v030_cognitive_template`;WS-E1 Step4 已让 `GRAPH.md` 和 phase frontmatter 接受统一 `iterate` 声明。LOGIC runtime 已收口为 plain dict + 纯返回写回,但仍有几处与 mvp1 目标不一致:LOGIC action 签名校验仍要求参数名 `context/ctx`；SUBGRAPH / agent `subgraphs[]` 仍是 `target_skill` 逻辑 id；SUBGRAPH 编译期仍做父子 IO 完整相等校验；AGENT body/mention 严格校验不完整；cognitive slot 文本/默认值与目标契约有漂移；validator 主要是 bool/占位契约,缺完整加载生命周期。

## UI/UX
N/A。

## 前端逻辑
N/A —— skill 源码语法被 Studio 编辑器/copilot 消费；本 baseline 只核代码解析层。

## 后端功能

### 1. 通用 Markdown/YAML 解析与路由
- Markdown frontmatter/body 拆分:`packages/graph-agent/src/graph_agent/core/parser.py:parse_markdown_parts` 读取 YAML frontmatter 与 raw body。
- 根编译主路径:`packages/graph-agent/src/graph_agent/core/loader.py:SkillLoader.compile_skill` 读取 `GRAPH.md`,再扫描 `phases/<id>/` 下的 phase 节点文件。
- phase 文件名到 mode 的映射:`packages/graph-agent/src/graph_agent/core/loader.py:_PHASE_FILE_TO_MODE` 固定 `LOGIC.md`→`logic`、`SUBGRAPH.md`→`subgraph`、`SKILL.md`→`agent`。
- phase AST 构建:`packages/graph-agent/src/graph_agent/core/loader.py:_build_phase_document` 注入内部 `mode`,再用 `LogicNodeAST` / `SubgraphNodeAST` / `AgentNodeAST` 做 Pydantic 校验。

### 2. GRAPH.md 现状
- 根 AST:`packages/graph-agent/src/graph_agent/core/manifest.py:GraphManifest` 当前字段为 `schema_version`、`name`、`description`、`io`、`phases`、`metadata`、`iterate`。
- inline IO 结构:`packages/graph-agent/src/graph_agent/core/manifest.py:PhaseIOSchema` 要求 `inputs` / `outputs` 两个 dict；`packages/graph-agent/src/graph_agent/core/loader.py:_reject_deprecated_physical_io` 禁 `io/inputs.json`、`io/outputs.json`；`packages/graph-agent/src/graph_agent/core/loader.py:_build_graph_manifest` 禁 `io_inputs_ref` / `io_outputs_ref`。
- 根版本/manifest 校验:`packages/graph-agent/src/graph_agent/core/loader.py:_build_graph_manifest` 要求 `schema_version == "v0.3.0"`、`phases` 是 list,再交给 `GraphManifest.model_validate`。
- body DAG 解析:`packages/graph-agent/src/graph_agent/core/loader.py:_extract_body_phase_refs` 解析 `<phase depends_on="...">name</phase>` 与 `output` flag。
- 拓扑校验:`packages/graph-agent/src/graph_agent/core/loader.py:_validate_graph_topology` 串起 `_validate_graph_phase_declarations`、`_validate_phase_name_sets`、`_validate_acyclic_graph`、`_validate_no_islands`、`_validate_unknown_dependencies`、`_validate_output_phases`、`_validate_phase_dir`。
- phase 节点唯一性:`packages/graph-agent/src/graph_agent/core/loader.py:_discover_phase_files` 要求每个 phase 目录恰好有 `LOGIC.md` / `SUBGRAPH.md` / `SKILL.md` 之一。

**GRAPH drift / refactor-target**:
- `packages/graph-agent/src/graph_agent/core/manifest.py:GraphManifest` 当前没有 `llm_role` 字段；目标语法有 graph 默认 `llm_role`。
- `packages/graph-agent/src/graph_agent/core/manifest.py:GraphManifest` 对 `name` 只做长度约束,未实现目标正则 `^[a-z][a-z0-9_-]*$`；`phases` item 也未逐项做正则。
- `packages/graph-agent/src/graph_agent/core/loader.py:_validate_output_phases` 当前要求至少一个 body `<phase output>`；目标语法允许未标记时由无下游节点推导输出候选。
- `packages/graph-agent/src/graph_agent/core/loader.py:_validate_inline_io_schema` 只调用 Draft 2020-12 `check_schema`,未强制顶层 `type: object` 或必须含 `properties`。
- 当前未见完整静态数据流“phase required 输入必须来自根输入或上游输出”的来源校验；`packages/graph-agent/src/graph_agent/core/loader.py:_validate_sequential_overwrites` 只处理上游输出字段覆盖授权。

### 3. LOGIC.md 现状
- AST:`packages/graph-agent/src/graph_agent/core/manifest.py:LogicNodeAST` 当前字段为 `mode`、`io`、`actions`、`validator`,并继承 `name`、`raw_blocks`、`metadata`、`allow_sequential_overwrite`、`batch`、`iterate`。
- body `<action>`:`packages/graph-agent/src/graph_agent/core/loader.py:_extract_logic_actions` 从 body 抽取 `<action>...</action>`；`packages/graph-agent/src/graph_agent/core/loader.py:_validate_logic_actions_declared` 要求 frontmatter `actions` 与 body 顺序完全一致。
- action 目录发现:`packages/graph-agent/src/graph_agent/core/loader.py:_discover_actions_and_tools` 只允许 LOGIC phase 有 `actions/`,并调用 `packages/graph-agent/src/graph_agent/core/loader.py:_load_action_dir` 加载 phase-local `actions/*.py`。
- action registry:`packages/graph-agent/src/graph_agent/core/actions.py:ActionDef` / `packages/graph-agent/src/graph_agent/core/actions.py:ActionRegistry` 保存并按 `phase_id + action_name` resolve。
- action 签名现状:`packages/graph-agent/src/graph_agent/core/loader.py:_validate_action_signature` 要求第一个参数名是 `context` 或 `ctx`,且注解兼容 `graph_agent.cognitive.context_facade.Context`。这仍是语法层 drift:目标签名命名是 `inputs`。
- LOGIC 运行装配:`packages/graph-agent/src/graph_agent/core/graph_assembler.py:_build_logic_node` 当前向 action 传入 plain dict `action_ctx = {**before, **updates}`；返回必须是 dict,返回 key 通过 `_validate_logic_update_keys` 限制在 `io.outputs`。`Context` mutation delta 已不再是 runtime 写回通道。
- 运行外层 StateMapper:`packages/graph-agent/src/graph_agent/core/graph_assembler.py:_wrap_phase_runtime_node` 用 `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:StateMapper` 包裹 LOGIC 节点,按 `io.inputs` 过滤输入、按 `io.outputs` 限制写回。
- purity 扫描:`packages/graph-agent/src/graph_agent/core/purity.py:scan_python_purity` 当前拦截 LOGIC action/tool 源码里的 LE2 hard-ban,包括 `run_skill` 编排、`open`/`io.open`、`pathlib.Path` 读/探测/枚举/stat/mutation、`os`/`os.path` FS 访问或变更、`shutil` 变更、`tempfile`、`glob`、`sys.path` mutation/赋值/删除、`importlib`/`__import__` 动态导入。

**LOGIC drift / refactor-target**:
- mvp1 目标是 `def <action_name>(inputs) -> dict`、只读 inputs、纯返回；当前 runtime 已传入 plain dict 并只写回返回 dict,但 `packages/graph-agent/src/graph_agent/core/loader.py:_validate_action_signature` 仍要求第一个参数名是 `context` 或 `ctx`。
- 当前 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:_build_logic_node` 已关闭 Context mutation delta 通道；若 action 对入参 dict 做本地 mutation,不会隐式写回 blackboard。
- 当前 `packages/graph-agent/src/graph_agent/core/loader.py:_load_action_dir` 发现本地 `actions/*.py` 中的任意本模块函数,未强制函数名必须等于文件名。
- 当前未见 Engine/Studio 通用 action registry 装配入口；`packages/graph-agent/src/graph_agent/core/actions.py:ActionRegistry` 只承载 loader 发现的 phase-local actions。
- 当前 `packages/graph-agent/src/graph_agent/core/purity.py:scan_python_purity` 已覆盖 `run_skill`、直接 FS、`sys.path` hack、动态 import 高风险路径；仍未覆盖非序列化对象返回,该项属于 LOGIC 运行/数据契约后续收口。
- validator 现状只在 AST 中有 `validator: StrictBool`;`packages/graph-agent/src/graph_agent/core/validator_contract.py:VALIDATOR_SIGNATURE` 只是占位契约,注释明确运行期 validator loading 在后续 PR；当前未见 LOGIC `validator.py` 缺失/entrypoint 的编译期加载校验,也未见 `_build_logic_node` 后置调用 validator。

### 4. SUBGRAPH.md 现状
- AST:`packages/graph-agent/src/graph_agent/core/manifest.py:SubgraphNodeAST` 当前字段为 `mode`、`target_skill`、`io`、`validator`,并继承 `name`、`raw_blocks`、`metadata`、`allow_sequential_overwrite`、`batch`、`iterate`。
- `target_skill` schema:`packages/graph-agent/src/graph_agent/core/manifest.py:SubgraphNodeAST` 使用 `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py:SKILL_ID_PATTERN`;agent `SKILL.md` 的 `subgraphs[]` 仍复用 `packages/graph-agent/src/graph_agent/core/manifest.py:AgentRegistryItem`,字段也是 `target_skill`。
- 编译期子图 IO 校验:`packages/graph-agent/src/graph_agent/core/loader.py:_validate_subgraph_io_contracts` 对每个 `SubgraphNodeAST` 调 `resolve_skill_root(resolver, doc.ast.target_skill)`,递归编译子图,再要求父 `SUBGRAPH.md io.inputs/outputs` 与子 `GRAPH.md io.inputs/outputs` 整个 schema 相等。
- 运行期子图装配:`packages/graph-agent/src/graph_agent/core/graph_assembler.py:_build_subgraph_node` 同样用 `resolve_skill_root(skill_resolver, phase_ast.target_skill)` 找子图 root,递归 assemble 后 invoke 子 graph。
- SUBGRAPH runtime 已被 StateMapper 包裹:`packages/graph-agent/src/graph_agent/core/graph_assembler.py:_wrap_phase_runtime_node` + `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:StateMapper` 会按父 `SUBGRAPH.md io.inputs` 切片,并按 `io.outputs` 限制合并。

**SUBGRAPH drift / refactor-target**:
- mvp1 目标字段是绝对 `path`;当前 `packages/graph-agent/src/graph_agent/core/manifest.py:SubgraphNodeAST` 和 `packages/graph-agent/src/graph_agent/core/manifest.py:AgentRegistryItem` 仍是 `target_skill` 逻辑 id。
- mvp1 目标无 registry 寻址;当前 `packages/graph-agent/src/graph_agent/core/loader.py:_validate_subgraph_io_contracts` 与 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:_build_subgraph_node` 仍调用 `resolve_skill_root(... target_skill)`。
- mvp1 目标放宽父子 IO,只按普通节点做 blackboard slice/merge；当前 `packages/graph-agent/src/graph_agent/core/loader.py:_validate_subgraph_io_contracts` 仍要求父子 `io.inputs/outputs` schema 完全相等。
- SUBGRAPH validator 当前只是 `SubgraphNodeAST.validator` bool 与 `validator_contract.py:VALIDATOR_SIGNATURE` 占位,未见 subgraph phase-local `validator.py` 加载/调用生命周期。

### 5. AGENT `SKILL.md` 现状
- AST:`packages/graph-agent/src/graph_agent/core/manifest.py:AgentNodeAST` 当前字段为 `mode`、`role`、`goal`、`steps`、`protocols`、`io`、`validator`、`tools`、`subagents`、`subgraphs`、`references`、`examples`、`examples_inline`、`max_iterations`、`llm_role`、`system_prompt`,并继承 `name`、`raw_blocks`、`metadata`、`allow_sequential_overwrite`、`batch`、`iterate`。
- Registry 子模型:`packages/graph-agent/src/graph_agent/core/manifest.py:SubagentSpec` 使用 `name` / `target_skill` / `description`;`packages/graph-agent/src/graph_agent/core/manifest.py:AgentRegistryItem` 也仍使用 `name` / `target_skill` / `description` 承载 `subgraphs[]`。
- phase 文档构建:`packages/graph-agent/src/graph_agent/core/loader.py:_build_phase_document` 对 `SKILL.md` 调 `packages/graph-agent/src/graph_agent/core/loader.py:_normalize_skill_node_frontmatter`,再调 `_parse_agent_body`,最后用 `AgentNodeAST.model_validate`。
- legacy 兼容入口:`packages/graph-agent/src/graph_agent/core/loader.py:_normalize_skill_node_frontmatter` 仍接受 `phase_config` 包装层,并把其中 `tools`、`subagents`、`subgraphs`、`references`、`examples`、`io`、`max_iterations`、`llm_role`、`validator`、`allow_sequential_overwrite`、`batch`、`iterate` 提到 Agent AST 数据。
- body 原始块提取:`packages/graph-agent/src/graph_agent/core/parser.py:extract_raw_blocks` 只按允许 tag 抽取每类第一个 raw block;`packages/graph-agent/src/graph_agent/core/loader.py:_parse_agent_body` 再检查允许 tag、禁止 `<steps>` 与 `<exit_contract>`、要求 `<role>` / `<goal>` 存在。
- body 列表解析:`packages/graph-agent/src/graph_agent/core/loader.py:_extract_agent_steps` 解析 `<step id name>`;`packages/graph-agent/src/graph_agent/core/loader.py:_extract_agent_protocols` 解析 `<protocol id>`;`packages/graph-agent/src/graph_agent/core/loader.py:_extract_agent_examples` 解析 `<example id>` 并检查 inline example id 唯一且正文非空。
- tool/action 物理目录发现:`packages/graph-agent/src/graph_agent/core/loader.py:_discover_actions_and_tools` 只允许 AGENT phase 有 `tools/`,并用 `packages/graph-agent/src/graph_agent/core/loader.py:_load_tool_dir` 加载 root/phase-local tools；`packages/graph-agent/src/graph_agent/core/actions.py:ToolRegistry` 产出 `StructuredTool`。
- subagent metadata:`packages/graph-agent/src/graph_agent/core/loader.py:_compile_subagent_metadata` 对 `subagents[]` 调 `resolve_skill_root(... target_skill)` 递归编译子 skill,并构建动态 subagent tool;`packages/graph-agent/src/graph_agent/core/loader.py:_inject_subagent_tools` 注入 `call_subagent_<name>`。
- AGENT 运行装配入口:`packages/graph-agent/src/graph_agent/core/graph_assembler.py:_build_skill_node` 解析模型、reference-reader markdown、business/framework tools、finish_task、cognitive middleware,再进入当前手写 tool-call loop。

**AGENT drift / refactor-target**:
- mvp1 目标要求 Agent `io.inputs` / `io.outputs` 必填；当前 `packages/graph-agent/src/graph_agent/core/manifest.py:AgentNodeAST` 将 `io` 定义为 `PhaseIOSchema | None`,且 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:_agent_system_prompt` 对 terminal phase 会 fallback 到 graph root outputs。
- mvp1 目标 `subgraphs[]` 子项是绝对 `path`;当前 `packages/graph-agent/src/graph_agent/core/manifest.py:AgentRegistryItem` 仍是 `target_skill` 逻辑 id。
- mvp1 目标未知字段直接按 AGENT schema 失败；当前 `packages/graph-agent/src/graph_agent/core/loader.py:_normalize_skill_node_frontmatter` 仍保留 legacy `phase_config` 包装层兼容。
- mvp1 目标 name/registry id 正则多处要求小写开头 `^[a-z][a-z0-9_-]*$` 或 body id `^[A-Z][A-Za-z0-9_-]*$`;当前 `AgentRegistryItem` / `SubagentSpec` 的 `name` 允许大写和下划线开头,`AgentStep` / `AgentProtocol` id 允许小写开头。
- mvp1 目标 `<role>` / `<goal>` 必须恰好 1 个,重复 fatal；当前 `packages/graph-agent/src/graph_agent/core/parser.py:extract_raw_blocks` 只取第一处,`packages/graph-agent/src/graph_agent/core/loader.py:_parse_agent_body` 未显式统计重复 `<role>` / `<goal>`。
- mvp1 目标 `<step>` / `<protocol>` / `<example>` id 在各自命名空间唯一；当前 `_extract_agent_examples` 检查 inline example 重复,但 `_extract_agent_steps` / `_extract_agent_protocols` 未显式检查重复 id。
- mvp1 目标 AGENT frontmatter `tools[]` 是暴露给 Agent 的工具清单；当前 `_build_skill_node` 会把 `compiled.tools.for_phase(phase_id)` 的 root/phase-local business tools 全部放入 `all_tools`,`phase_ast.tools` 主要用于 framework/critic tool 校验。

### 6. cognitive 模板现状
- 模板函数:`packages/graph-agent/src/graph_agent/cognitive/prompt.py:apply_v030_cognitive_template` 直接生成 V0.3.0 Agent phase 的 8 槽 prompt + 末尾 `<exit_contract>`。
- exit contract 文本:`packages/graph-agent/src/graph_agent/cognitive/prompt.py:V030_AGENT_EXIT_CONTRACT_TEXT` 固定 finish_task 输出说明。
- role prefix seam:`packages/graph-agent/src/graph_agent/cognitive/prompt.py:resolve_role_prefix_from_llm_role` 当前总是返回空字符串,注释说明 Provider Intelligence V2 已把 role prefix 应用移到 `graph_agent_gateway.GatewayChatModel`。
- AGENT prompt 入口:`packages/graph-agent/src/graph_agent/core/graph_assembler.py:_agent_system_prompt` 把 `AgentNodeAST` 的 `role`、`goal`、`steps`、`protocols`、`examples_inline`、`references`、document `examples` 和 output schema 传给 `apply_v030_cognitive_template`。
- reference/example registry 文本:`packages/graph-agent/src/graph_agent/core/graph_assembler.py:_reference_registry_listing` / `packages/graph-agent/src/graph_agent/core/graph_assembler.py:_example_registry_listing` 分别产出 `- id: summary` 列表或默认中文文案。
- reference-reader 预读:`packages/graph-agent/src/graph_agent/core/graph_assembler.py:_build_reference_reader_markdown` 在装配 AGENT node 时用 `packages/graph-agent/src/graph_agent/core/builtin_subagents/reference_reader.py:ReferenceReaderRuntime`(经 `core/builtin_subagents/__init__.py` re-export)生成 knowledge_base markdown。

**cognitive drift / refactor-target**:
- mvp1 目标 `{llm_role_prefix_section}` 来源是 `llm_roles.yaml system_prompt_prefix`;当前 `resolve_role_prefix_from_llm_role` 在 Engine 内恒返回 `""`,role prefix 实际下沉到 gateway。
- mvp1 目标 `{skill_steps_splat}` 空值允许为空字符串；当前 `apply_v030_cognitive_template` 输出 `"无显式步骤"`。
- mvp1 目标 `{skill_examples_inline}` 默认 `"无内联示例"`；当前代码默认 `"无内联示范"`。
- mvp1 目标 `{output_schema}` 来自当前 Agent phase `io.outputs`;当前 `_agent_system_prompt` 若 Agent `io` 缺失且 phase 是 terminal,会 fallback 到 graph root outputs。
- mvp1 目标模板语法中的 `<knowledge_base>` 文案要求 reader 失败降级警告 + 原文摘录；当前 `apply_v030_cognitive_template` 本身只接收已经生成的 `knowledge_base_markdown`,失败降级逻辑在 `_build_reference_reader_markdown` / `ReferenceReaderRuntime` 路径上。

### 7. mention 现状
- mention token 模型:`packages/graph-agent/src/graph_agent/core/mentions.py:Mention` 当前只记录 `kind`、`name`、`start`。
- 合法 token 扫描:`packages/graph-agent/src/graph_agent/core/mentions.py:MENTION_RE` 正则为 `@(subagent|tool|subgraph|protocol|step|reference|example):([A-Za-z0-9_-]+)`;`packages/graph-agent/src/graph_agent/core/mentions.py:scan_mentions` 返回所有匹配项。
- 残缺 token 扫描:`packages/graph-agent/src/graph_agent/core/mentions.py:BROKEN_MENTION_RE` 只匹配 7 类 type 后面没有冒号的写法;`packages/graph-agent/src/graph_agent/core/mentions.py:first_broken_mention` 返回第一处。
- 静态可达性校验:`packages/graph-agent/src/graph_agent/core/loader.py:_validate_agent_mentions` 先检查 broken mention,再构建 `subagent`、`subgraph`、`reference`、`example`、`step`、`protocol`、`tool` 七个 domain 并扫描整个 body。
- tool 可达域:`packages/graph-agent/src/graph_agent/core/loader.py:_validate_agent_mentions` 当前把 `phase_ast.tools` 加上 builtin `finish_task`、`read_reference`、`read_example`、`log_ambiguity` 作为 `@tool` 可达集合。

**mention drift / refactor-target**:
- mvp1 目标 mention ref 至少带 `type/name/source_tag/source_id/span`;当前 `Mention` 只有 `kind/name/start`,缺 `source_tag` 与 `source_id`。
- mvp1 目标 Loader 只扫描 Agent body XML 文本节点；当前 `_validate_agent_mentions` 对整个 raw body 字符串扫描,没有区分 XML 文本节点、属性或其他上下文。
- mvp1 目标未知 type 如 `@asset:R1` FATAL；当前 `MENTION_RE` 不匹配未知 type,`BROKEN_MENTION_RE` 也只覆盖 7 类已知 type,因此未知 type 会被当普通文本忽略。
- mvp1 目标残缺 token 如 `@reference:` FATAL；当前 `BROKEN_MENTION_RE` 对 type 后已有冒号但缺 name 的情况不匹配,因此 `@reference:` 会被忽略。
- mvp1 目标聚合全部不可达 ref 一次报错；当前 `_validate_agent_mentions` 遇到第一处不可达 mention 即 `_fatal`。
- mvp1 目标 `@subgraph` 额外校验 `path` 绝对路径/可解析；当前 `subgraph` domain 来自 `AgentRegistryItem.name`,而 `AgentRegistryItem` 子项仍是 `target_skill`。
- mvp1 目标未使用注册项 WARN `[F-v3-mention-unused-registry-entry]`;当前未见对应 unused registry 扫描。

### 8. iterate 声明现状(WS-E1 Step4 已落)
- 统一声明模型:`packages/graph-agent/src/graph_agent/core/manifest.py:IterateSpec` 当前字段为 `mode`、`over`、`item_var`、`range`、`concurrency`、`accumulate`。
- accumulator 子模型:`packages/graph-agent/src/graph_agent/core/manifest.py:IterateAccumulateSpec` 当前字段为 `var`、`init`、`from`、`merge`;`merge` 只接受 `append`、`extend`、`merge`、`replace`。
- graph-level 声明:`packages/graph-agent/src/graph_agent/core/manifest.py:GraphManifest.iterate` 允许 `GRAPH.md` frontmatter 写 `iterate`。
- phase-level 声明:`LogicNodeAST` / `SubgraphNodeAST` / `AgentNodeAST` 均继承 `_BaseNodeAST.iterate`,允许 phase frontmatter 写 `iterate`。
- legacy 兼容:`BatchSpec` 与 `_BaseNodeAST.batch` 仍保留,旧 `batch:{iterator,item_var,concurrency}` 继续接受。
- 编译期 loop 字段校验:`packages/graph-agent/src/graph_agent/core/loader.py:_validate_iterate_compile_contracts` 要求 loop phase `io.inputs` 同时声明 `item_var` 与 `accumulate.var`,否则 `[F-v3-iterate-accumulate-fields-missing]`。

**iterate drift / refactor-target**:
- 语法层已支持 `iterate`,但 graph-level batch 当前运行实现不是 LangGraph `Send` 专门 API;执行细节见 `02-mechanism/04-run-outer/02-iterate/baseline.md`。
- Step4 未扩展 callbacks/events trace schema,因此 `phase_execution_id` / `iteration_index` 的事件消费仍归后续 observability。

## API
- 根 AST:`packages/graph-agent/src/graph_agent/core/manifest.py:GraphManifest`
- phase AST union:`packages/graph-agent/src/graph_agent/core/manifest.py:PhaseAST`
- LOGIC AST:`packages/graph-agent/src/graph_agent/core/manifest.py:LogicNodeAST`
- SUBGRAPH AST:`packages/graph-agent/src/graph_agent/core/manifest.py:SubgraphNodeAST`
- AGENT AST:`packages/graph-agent/src/graph_agent/core/manifest.py:AgentNodeAST`
- AGENT body 子 AST:`packages/graph-agent/src/graph_agent/core/manifest.py:AgentStep` / `AgentProtocol` / `AgentExample`
- AGENT registry 子 AST:`packages/graph-agent/src/graph_agent/core/manifest.py:SubagentSpec` / `AgentRegistryItem` / `ReferenceSpec` / `ExampleSpec`
- iterate AST:`packages/graph-agent/src/graph_agent/core/manifest.py:IterateSpec` / `IterateAccumulateSpec`
- mention scanner:`packages/graph-agent/src/graph_agent/core/mentions.py:scan_mentions`
- cognitive template:`packages/graph-agent/src/graph_agent/cognitive/prompt.py:apply_v030_cognitive_template`
- 编译产物:`packages/graph-agent/src/graph_agent/core/loader.py:CompiledSkill`
- phase 文档:`packages/graph-agent/src/graph_agent/core/loader.py:PhaseDocument`
- action registry:`packages/graph-agent/src/graph_agent/core/actions.py:ActionRegistry`
- tool registry:`packages/graph-agent/src/graph_agent/core/actions.py:ToolRegistry`

## Data Model / State
skill 源码(语法)→ `CompiledSkill` → LangGraph node:
- `GRAPH.md` frontmatter/body 产出 `GraphManifest` + `raw["graph_topology"]`。
- `LOGIC.md` 产出 `LogicNodeAST`,再由 `graph_assembler.py:_build_logic_node` 转成运行节点。
- `SUBGRAPH.md` 产出 `SubgraphNodeAST`,再由 `graph_assembler.py:_build_subgraph_node` 转成子图 invoke 节点。
- `SKILL.md` 产出 `AgentNodeAST`;body 5 类 XML 块变成 `role` / `goal` / `steps` / `protocols` / `examples_inline`;frontmatter registry 变成 `tools` / `subagents` / `subgraphs` / `references` / document `examples`。
- mention 扫描当前只产生 `Mention(kind,name,start)`,再由 `loader.py:_validate_agent_mentions` 按 Agent AST 本地集合查可达域。
- cognitive prompt 当前由 `graph_assembler.py:_agent_system_prompt` 收集 Agent AST + reference/example listing + output schema,再交 `cognitive/prompt.py:apply_v030_cognitive_template` 渲染。
- `StateMapper` 现已承担 phase 输入切片和输出字段限制,但若编译期旧校验拦住,子图 path/io 放宽目标仍无法成立；Agent `io` 允许缺失也会让 mvp1 必填目标不成立。
- `iterate` 源码语法进入 `GraphManifest.iterate` 或 phase AST `iterate`,运行时由 `02-iterate` 的 graph/phase wrapper 消费。

## 当前边界(这个模块现在不是什么)
- 不是运行机制最终真相:LOGIC 运行外层决策归 `02-mechanism/04-run-outer/01-graph-exec`,本文只记录 skill 语法现状。
- 不是 resolver 真相:子图 `target_skill`→path 的旧解析现状归 `02-mechanism/02-resolver` 也有 baseline；本文只写语法字段现状。
- 不是 cognitive 渲染机制最终真相:渲染流程归 `02-mechanism/03-assemble`,本文只记录模板语法相关代码现状。
- resource / io 切片语法还未在本批展开；iterate 语法已由 WS-E1 Step4 落地。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| GRAPH `name`/phase id 命名 | `GraphManifest.name` 只长度约束；phase item 未逐项正则 | `^[a-z][a-z0-9_-]*$` |
| GRAPH `llm_role` | `GraphManifest` 无字段 | 可选,默认 `"analyst"`,必须已注册 |
| GRAPH `iterate` | `GraphManifest.iterate` 已支持 `iterate:{mode,over,item_var,range,concurrency,accumulate}` | 对齐基础语法 |
| GRAPH output phase | `_validate_output_phases` 要求显式 `<phase output>` | 可显式多个；未标记时由无下游节点推导 |
| GRAPH inline IO object | `_validate_inline_io_schema` 只 `check_schema` | 顶层 `type: object` 且含 `properties` |
| GRAPH 静态数据流 | 未见 required 来源完整校验 | required 必须来自根输入或上游输出 |
| LOGIC action 签名 | `_validate_action_signature` 仍要求参数名 `context/ctx` + `Context` 兼容注解 | `def <action_name>(inputs) -> dict` |
| LOGIC action 写状态 | runtime 已关闭 Context mutation delta,只写回 action 返回 dict | 只读 inputs,纯返回 dict,不写黑板 |
| LOGIC purity | 已挡 `run_skill`、直接 FS、`sys.path`、动态 import 高风险路径；仍未挡非序列化返回 | 继续收口非序列化返回与纯 action 数据契约 |
| LOGIC validator | bool + `VALIDATOR_SIGNATURE` 占位,未见加载/调用 | `validator: true` 必须加载同级 `validator.py` 并后置阻断 |
| phase `iterate` | LOGIC/SUBGRAPH/AGENT 共享 AST 已支持 `iterate`;旧 `batch` 兼容 | 对齐基础语法;旧 `batch` 迁移期兼容 |
| SUBGRAPH 寻址字段 | `target_skill` 逻辑 id | `path` 绝对路径 |
| SUBGRAPH resolver | `resolve_skill_root(... target_skill)` | 直接按绝对 path 解析,无 registry |
| SUBGRAPH IO | 编译期父子 schema 完整相等 | 普通节点黑板切片/合并,不强制父子 1:1 |
| AGENT `io` | `AgentNodeAST.io` 可为 `None`;terminal phase 可 fallback 到 graph outputs | `io.inputs` / `io.outputs` 必填 |
| AGENT `subagents[]` | `SubagentSpec(name,target_skill,description)` | 保持 `target_skill`,按子代理机制校验 |
| AGENT `subgraphs[]` | `AgentRegistryItem(name,target_skill,description)` | `name,path,description`,其中 `path` 为绝对路径 |
| AGENT legacy frontmatter | `_normalize_skill_node_frontmatter` 接受 `phase_config` 包装层,并透传 `iterate` | 直接 AGENT frontmatter;未知字段 fatal |
| AGENT 命名/ID | registry name 可大写/下划线开头;step/protocol id 可小写开头 | registry name 小写规则;body id 大写开头规则 |
| AGENT body `<role>/<goal>` | `extract_raw_blocks` 取第一处,未显式报重复 | 恰好 1 个,缺失/重复均 fatal |
| AGENT body 列表 id | inline example 查重复;step/protocol 未显式查重复 | step/protocol/example 各命名空间唯一 |
| AGENT tools 暴露 | root/phase-local business tools 全部进入 `all_tools`;`tools[]` 主要校验 framework/critic 名 | `tools[]` 是暴露给 Agent 的工具清单 + builtin |
| cognitive role prefix | `resolve_role_prefix_from_llm_role` 恒返回 `""` | `{llm_role_prefix_section}` 来自 `llm_roles.yaml system_prompt_prefix` |
| cognitive slot 默认值 | steps 默认 `"无显式步骤"`;inline example 默认 `"无内联示范"` | steps 可空;inline example 默认 `"无内联示例"` |
| cognitive output schema | Agent `io` 缺失时 terminal phase fallback 到 graph outputs | 来自当前 Agent phase `io.outputs` |
| mention ref 模型 | `Mention(kind,name,start)` | 至少含 `type/name/source_tag/source_id/span` |
| mention 扫描范围 | `_validate_agent_mentions` 扫整个 raw body | 只扫 Agent body XML 文本节点 |
| mention 语法错误 | 未知 type 和 `@reference:` 会被忽略 | 未知 type / 残缺 token fatal |
| mention 缺失聚合 | 第一处不可达即 fatal | 聚合全部不可达 ref 一次报错 |
| mention unused registry | 未见 unused registry WARN | 未使用注册项 WARN |

> **验"是否按 mvp1 改了"**:① GRAPH name/phase/io/output/dataflow 按目标收紧或推导；② GRAPH/phase `iterate` 是否按 `IterateSpec` 接受统一语法、旧 `batch` 仅兼容；③ LOGIC runtime 是否不再接受可变 `Context` 写回、只通过返回 dict 更新 blackboard,同时 action 签名命名最终收敛到 `inputs`;④ `run_skill`/FS/sys.path/import 越界保持编译期 purity FATAL,非序列化返回继续收口；⑤ LOGIC/SUBGRAPH/AGENT validator 生命周期真正加载同级 `validator.py`;⑥ SUBGRAPH / agent `subgraphs[]` 解析 `path` 绝对路径,旧 `target_skill` 报未知字段；⑦ 移除/反转 `_validate_subgraph_io_contracts` 的父子 1:1 schema 相等门；⑧ Agent `io` 必填、body 重复/id 唯一/mention 严格校验按目标生效；⑨ cognitive slot 文本、默认值和 output_schema 来源与目标一致。

## 读代码主路径提示
GRAPH: `loader.py:SkillLoader.compile_skill` → `parser.py:parse_markdown_parts` → `loader.py:_build_graph_manifest` → `loader.py:_extract_body_phase_refs` → `loader.py:_validate_graph_topology` → `loader.py:_discover_phase_files`。

LOGIC: `loader.py:_build_phase_document` → `manifest.py:LogicNodeAST` → `loader.py:_extract_logic_actions` / `_validate_logic_actions_declared` → `loader.py:_discover_actions_and_tools` / `_load_action_dir` → `graph_assembler.py:_build_logic_node` → `runtime/state_mapper.py:StateMapper`。

SUBGRAPH: `loader.py:_build_phase_document` → `manifest.py:SubgraphNodeAST` → `loader.py:_validate_subgraph_io_contracts` → `graph_assembler.py:_build_subgraph_node` → `runtime/state_mapper.py:StateMapper`。

AGENT: `loader.py:_build_phase_document` → `loader.py:_normalize_skill_node_frontmatter` → `loader.py:_parse_agent_body` → `manifest.py:AgentNodeAST` → `loader.py:_validate_agent_mentions` → `loader.py:_compile_subagent_metadata` / `_inject_subagent_tools` → `graph_assembler.py:_build_skill_node`。

cognitive: `graph_assembler.py:_agent_system_prompt` → `cognitive/prompt.py:resolve_role_prefix_from_llm_role` → `cognitive/prompt.py:apply_v030_cognitive_template`。

mention: `core/mentions.py:scan_mentions` / `first_broken_mention` → `loader.py:_validate_agent_mentions`。

iterate: `manifest.py:IterateSpec` / `IterateAccumulateSpec` → `GraphManifest.iterate` 或 `_BaseNodeAST.iterate` → `loader.py:_validate_iterate_compile_contracts` → `02-iterate` runtime wrapper。

## 交叉引用(链接, 不复制)
`mvp1-alignment`(目标) · `01-physical-layout`(文件位置/节点唯一) · `03-compile-rules`(错误码全表) · `02-mechanism/02-resolver`(path 解析目标) · `02-mechanism/03-assemble`(cognitive 渲染) · `02-mechanism/04-run-outer/01-graph-exec`(LOGIC V4 / StateMapper) · `02-mechanism/05-run-inner/04-tools`(Agent tools)
