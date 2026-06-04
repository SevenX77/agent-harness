# skill-compilation (engine) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: V2.1 技能目录解析、AST 构建、图拓扑校验、静态 IO 数据流校验 (audit A7/A8)、编译缓存策略
> **配套**: 见 [INDEX.md](../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

这里的 "backend Python library" 指 `packages/graph-agent` 里的 Python 引擎代码，不是 Studio 的 FastAPI 后端，也不是 React 前端。用户不会直接在界面上看到 "compile" 这个模块的状态；它只通过调用方拿到的异常、返回对象或后续 runtime 行为体现结果。

## 前端逻辑

N/A — 此模块为纯 backend Python library, 无 UI / 无前端调用面。

Studio 画布或编辑器可能间接依赖编译结果，但本 baseline 描述的是 `graph_agent.core.compiler` / `graph_agent.core.loader` / `graph_agent.core.cache` 的当下实现。React 侧没有直接参与 `GRAPH.md` 解析、phase AST 构建、拓扑校验或 Python action 加载。

## 后端功能

### 总入口和返回对象 {#cross-skill-compilation-compiled-skill}

当前公开编译入口是 `compile_skill(root, *, chat_model=None, cache=True) -> CompiledSkill`，定义在 `packages/graph-agent/src/graph_agent/core/compiler.py:40`。`chat_model` 参数被保留在签名里，但编译阶段会 `del chat_model`，说明现在编译本身不需要模型，模型只在 graph 装配和执行阶段使用，代码位置是 `packages/graph-agent/src/graph_agent/core/compiler.py:48` 和 `packages/graph-agent/src/graph_agent/core/compiler.py:52`。

`CompiledSkill` 是编译产物的核心数据结构，包含 `raw`、`manifest`、`nodes`、`actions`、`tools`、`subagents_by_phase`、`phase_tokens`，定义在 `packages/graph-agent/src/graph_agent/core/loader.py:65` 到 `packages/graph-agent/src/graph_agent/core/loader.py:75`。人话说，`CompiledSkill` 就是 "已经读懂的 skill 目录"：根图声明已经变成 `GraphManifest`，每个 phase 文件已经变成 `PhaseDocument`，Python action/tool 已经加载成 registry，subagent metadata 也被归到对应父 phase。

这份编译产物会被 execution runtime 接着装配成 LangGraph。调用方如何消费 `CompiledSkill`，详见 [execution-runtime/baseline.md#后端功能](../execution-runtime/baseline.md#后端功能)。

### V0.3 skill root 守卫

`SkillLoader.compile_skill()` 是实际编译器主体，定义在 `packages/graph-agent/src/graph_agent/core/loader.py:142`。第一步是 `_guard_v21_root(root)`，位置是 `packages/graph-agent/src/graph_agent/core/loader.py:144`。这个守卫要求入口必须是目录，不能是旧的根级 `SKILL.md` 单文件，因为 `_guard_v21_root` 在 `packages/graph-agent/src/graph_agent/core/loader.py:256` 到 `packages/graph-agent/src/graph_agent/core/loader.py:272` 明确检查目录存在、`GRAPH.md` 存在、`phases/` 存在且至少有 phase 子目录。

如果 skill root 里存在旧 schema 2.0 风格的根级 `SKILL.md`，编译器会报 `[F-v21-route]`，代码在 `packages/graph-agent/src/graph_agent/core/loader.py:262` 到 `packages/graph-agent/src/graph_agent/core/loader.py:264`。这就是 audit 里说当前真实支持的是目录型 V2.1 skill，而不是单文件 `SKILL.md` 的原因，背景见 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:37`。

### `GRAPH.md` 解析和 manifest 构建

`GRAPH.md` 是根图声明文件。编译器读取它在 `packages/graph-agent/src/graph_agent/core/loader.py:146` 到 `packages/graph-agent/src/graph_agent/core/loader.py:150`：先读文本，再拆 frontmatter/body，再从 body 里抽 `<phase .../>` 标签，最后构建 `GraphManifest`。

`GraphManifest` 是 Pydantic 模型，定义在 `packages/graph-agent/src/graph_agent/core/manifest.py:45` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:56`。它的默认 IO 引用是 `io/inputs.json` 和 `io/outputs.json`，对应 `packages/graph-agent/src/graph_agent/core/manifest.py:53` 和 `packages/graph-agent/src/graph_agent/core/manifest.py:54`。

`<input />`、`<output />`、`<phase />` 标签的解析在 `_build_graph_manifest()` 里完成。`_first_src(body, "input")` 和 `_first_src(body, "output")` 把 body 中的输入输出引用写回 manifest 数据，代码在 `packages/graph-agent/src/graph_agent/core/loader.py:613` 到 `packages/graph-agent/src/graph_agent/core/loader.py:618`。phase 标签被转成 `GraphPhaseRef`，代码在 `packages/graph-agent/src/graph_agent/core/loader.py:620` 到 `packages/graph-agent/src/graph_agent/core/loader.py:631`。

`GraphPhaseRef` 是单个 phase 引用，包含 `id`、`src`、`depends_on`，定义在 `packages/graph-agent/src/graph_agent/core/manifest.py:16` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:23`。`depends_on` 是拓扑依赖，不是数据依赖；也就是说它只说明执行顺序，不说明哪些字段从上游流向下游。

### phase 文件发现和 AST 构建

V2.1 phase 只认三种物理文件名：`LOGIC.md`、`SUBGRAPH.md`、`SKILL.md`，映射表在 `packages/graph-agent/src/graph_agent/core/loader.py:46` 到 `packages/graph-agent/src/graph_agent/core/loader.py:50`。`_discover_phase_files()` 遍历 `phases/*`，禁止一个 phase 目录同时包含多个 node 文件，代码在 `packages/graph-agent/src/graph_agent/core/loader.py:277` 到 `packages/graph-agent/src/graph_agent/core/loader.py:299`。

每个 phase 文件会被 `parse_markdown_parts()` 拆 frontmatter 和正文，然后 `_validate_mode_matches_filename()` 校验 frontmatter 里的 `mode` 必须和文件名一致，主循环在 `packages/graph-agent/src/graph_agent/core/loader.py:158` 到 `packages/graph-agent/src/graph_agent/core/loader.py:167`，mode 校验在 `packages/graph-agent/src/graph_agent/core/loader.py:594` 到 `packages/graph-agent/src/graph_agent/core/loader.py:601`。

AST 是 "Abstract Syntax Tree" 的简称，这里不是 Python AST，而是把 Markdown frontmatter/body 解析成强类型对象。`LogicNodeAST`、`SubgraphNodeAST`、`SkillNodeAST` 分别定义在 `packages/graph-agent/src/graph_agent/core/manifest.py:69`、`packages/graph-agent/src/graph_agent/core/manifest.py:76`、`packages/graph-agent/src/graph_agent/core/manifest.py:83`。例如 `SkillNodeAST` 要求 `system_prompt`、`exit_contract`、`tools`、`subagents`，代码在 `packages/graph-agent/src/graph_agent/core/manifest.py:86` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:90`。

### 拓扑校验

拓扑校验入口是 `_validate_graph_topology(graph_path, raw_attrs, root)`，调用点在 `packages/graph-agent/src/graph_agent/core/loader.py:152`，实现从 `packages/graph-agent/src/graph_agent/core/loader.py:730` 开始。

当前校验包含几类：

- phase 必须有 `id` 和 `src`，见 `packages/graph-agent/src/graph_agent/core/loader.py:735` 到 `packages/graph-agent/src/graph_agent/core/loader.py:739`。
- phase id 不能重复，见 `packages/graph-agent/src/graph_agent/core/loader.py:741` 到 `packages/graph-agent/src/graph_agent/core/loader.py:746`。
- `depends_on` 必须显式存在；入口 phase 要写 `depends_on=""`，见 `packages/graph-agent/src/graph_agent/core/loader.py:747` 到 `packages/graph-agent/src/graph_agent/core/loader.py:753`。
- 依赖不能指向未知 phase，也不能自环，见 `packages/graph-agent/src/graph_agent/core/loader.py:755` 到 `packages/graph-agent/src/graph_agent/core/loader.py:765`。
- `_validate_acyclic_graph()` 检测环，见 `packages/graph-agent/src/graph_agent/core/loader.py:774` 到 `packages/graph-agent/src/graph_agent/core/loader.py:805`。
- `_validate_no_orphans()` 检测孤岛，见 `packages/graph-agent/src/graph_agent/core/loader.py:807` 到 `packages/graph-agent/src/graph_agent/core/loader.py:837`。
- `_validate_phase_src()` 确认 `src` 在 skill root 内且目标目录有三种 phase 文件之一，见 `packages/graph-agent/src/graph_agent/core/loader.py:839` 到 `packages/graph-agent/src/graph_agent/core/loader.py:858`。

### IO schema 校验

IO schema 指 JSON Schema 文件，不是 runtime 输入漏斗。当前编译器会读取并校验 `io/inputs.json` 和 `io/outputs.json` 的 JSON Schema 合法性，调用点在 `packages/graph-agent/src/graph_agent/core/loader.py:153` 和 `packages/graph-agent/src/graph_agent/core/loader.py:154`。

`_validate_io_schema()` 会确认引用路径在 skill root 内、后缀是 `.json`、文件存在、JSON 可解析、schema 是对象，并用 Draft 2020-12 校验 schema 自身，代码在 `packages/graph-agent/src/graph_agent/core/loader.py:874` 到 `packages/graph-agent/src/graph_agent/core/loader.py:900`。这解释了当前 "IO" 的编译期含义：它能确认 schema 文件像不像 schema，但还没有把每个 phase 的输入输出映射成数据流图。

### actions/tools 发现和纯净性扫描

`_discover_actions_and_tools()` 在 `packages/graph-agent/src/graph_agent/core/loader.py:302` 到 `packages/graph-agent/src/graph_agent/core/loader.py:337`。当前规则是：

- root 级 `tools/` 可以存在并被加载，见 `packages/graph-agent/src/graph_agent/core/loader.py:308` 到 `packages/graph-agent/src/graph_agent/core/loader.py:312`。
- LOGIC phase 只允许 `actions/`，不允许 `tools/`，见 `packages/graph-agent/src/graph_agent/core/loader.py:319` 到 `packages/graph-agent/src/graph_agent/core/loader.py:323`。
- SKILL phase 只允许 `tools/`，不允许 `actions/`，见 `packages/graph-agent/src/graph_agent/core/loader.py:324` 到 `packages/graph-agent/src/graph_agent/core/loader.py:328`。
- SUBGRAPH phase 不允许 `actions/` 或 `tools/`，见 `packages/graph-agent/src/graph_agent/core/loader.py:329` 到 `packages/graph-agent/src/graph_agent/core/loader.py:333`。

纯净性扫描是为了阻止业务 action/tool 直接做危险文件系统写入。`_raise_on_purity_violations()` 调 `scan_python_purity()`，代码在 `packages/graph-agent/src/graph_agent/core/loader.py:523` 到 `packages/graph-agent/src/graph_agent/core/loader.py:527`。action 加载时调用它，见 `packages/graph-agent/src/graph_agent/core/loader.py:492` 到 `packages/graph-agent/src/graph_agent/core/loader.py:505`；tool 加载时也调用它，并额外禁止 tool import `graph_agent.cognitive.context_facade`，见 `packages/graph-agent/src/graph_agent/core/loader.py:508` 到 `packages/graph-agent/src/graph_agent/core/loader.py:520`。

### 静态写键校验

编译器会从 input/output schema 的 `properties` 抽出允许 key，调用点在 `packages/graph-agent/src/graph_agent/core/loader.py:155` 和 `packages/graph-agent/src/graph_agent/core/loader.py:156`。`_extract_output_schema_keys()` 的实现只看 schema 顶层 `properties`，见 `packages/graph-agent/src/graph_agent/core/loader.py:903` 到 `packages/graph-agent/src/graph_agent/core/loader.py:909`。

LOGIC action 的静态写键校验入口是 `_validate_logic_action_return_keys()`，调用点在 `packages/graph-agent/src/graph_agent/core/loader.py:169` 到 `packages/graph-agent/src/graph_agent/core/loader.py:175`，实现从 `packages/graph-agent/src/graph_agent/core/loader.py:964` 到 `packages/graph-agent/src/graph_agent/core/loader.py:989`。它把 `return {"key": ...}` 限制在 output schema keys，把 `ctx.update(key=value)` / `context.update(key=value)` 限制在 input+output schema keys。

实际 AST visitor 在 `packages/graph-agent/src/graph_agent/core/loader.py:912` 到 `packages/graph-agent/src/graph_agent/core/loader.py:954`。注意这里校验的是 Python 源码静态形态，不等于完整 phase-level IO contract。比如动态 key、复杂数据依赖、下游 required input 是否有上游产出，都不是这段代码能完整证明的。

### subagent metadata 编译和动态工具注入

`subagent` 第一次出现时需要定义：它是 SKILL phase 里 LLM 可以调用的子 agent；在当前代码里，subagent 不是一个单独 `SKILL.md`，而是一个完整 V0.3 skill root。父 `SKILL.md` 的 `phase_config.subagents` 被归一化进 `SkillNodeAST.subagents`，而 `SubagentSpec` 定义在 `packages/graph-agent/src/graph_agent/core/manifest.py:35` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:42`。

编译器在 `packages/graph-agent/src/graph_agent/core/loader.py:176` 调 `_compile_subagent_metadata()`，实现从 `packages/graph-agent/src/graph_agent/core/loader.py:340` 到 `packages/graph-agent/src/graph_agent/core/loader.py:384`。它会解析 subagent path、递归编译子 skill、读取子 skill 的 `io.inputs`，并用这个 schema 生成 Pydantic 输入模型。

`_resolve_subagent_root()` 要求 subagent path 是相对路径、不能跑出父 skill root、目标目录存在且有 `GRAPH.md`，见 `packages/graph-agent/src/graph_agent/core/loader.py:447` 到 `packages/graph-agent/src/graph_agent/core/loader.py:483`。`_inject_subagent_tools()` 会为每个 subagent 生成 `call_subagent_<name>` 动态工具，代码在 `packages/graph-agent/src/graph_agent/core/loader.py:387` 到 `packages/graph-agent/src/graph_agent/core/loader.py:407`；工具定义在 `packages/graph-agent/src/graph_agent/core/loader.py:410` 到 `packages/graph-agent/src/graph_agent/core/loader.py:437`。

### 编译 cache

`compile_skill()` 默认 `cache=True`，所以会先算 cache key，再 `load_from_cache()`，命中就直接返回 cached `CompiledSkill`，代码在 `packages/graph-agent/src/graph_agent/core/compiler.py:54` 到 `packages/graph-agent/src/graph_agent/core/compiler.py:58`。未命中时调用 `SkillLoader().compile_skill()`，再 `save_to_cache()`，代码在 `packages/graph-agent/src/graph_agent/core/compiler.py:60` 到 `packages/graph-agent/src/graph_agent/core/compiler.py:63`。

cache key 由 root、Python 版本、包版本、skill 文件元数据组成，见 `packages/graph-agent/src/graph_agent/core/cache.py:22` 到 `packages/graph-agent/src/graph_agent/core/cache.py:31`。`_collect_skill_files()` 只收集 `GRAPH.md`、`io/*.json`、`phases/**/*.md`，见 `packages/graph-agent/src/graph_agent/core/cache.py:55` 到 `packages/graph-agent/src/graph_agent/core/cache.py:66`。

cache 默认目录是 `Path.home() / ".cache" / "graph-agent-v21"`，见 `packages/graph-agent/src/graph_agent/core/cache.py:18` 到 `packages/graph-agent/src/graph_agent/core/cache.py:19`。`save_to_cache()` 直接 `mkdir` 和 `write_text`，没有 try/except 降级，见 `packages/graph-agent/src/graph_agent/core/cache.py:45` 到 `packages/graph-agent/src/graph_agent/core/cache.py:52`。

## API

### Python public surface

`compile_skill(root, *, chat_model=None, cache=True)` 是本 feature 的公开入口，代码在 `packages/graph-agent/src/graph_agent/core/compiler.py:40` 到 `packages/graph-agent/src/graph_agent/core/compiler.py:45`。返回值是 `CompiledSkill`，它不是 JSON 响应，而是 Python 内存对象。

`SkillLoader.compile_skill(skill_root, *, skill_resolver=...)` 是底层 loader API。内部实现仍会直接抛 leaf class，例如 `SkillLoadError` 或 `GraphAgentFatalError`；PR-A 后这些 leaf 分别是 public family `GraphCompileError` / `GraphExecutionError` 的 implementation detail。对外调用方不应按 leaf class 分支，而应 catch family 并读取 `exc.payload.code`。当前错误码使用 `[F-v3-...]` 细码并由 `ERROR_REGISTRY` 补齐 `level`、`stage`、`doc_link`，旧 `[F-v21-route]` / `[F-v21-io]` / `[F-v21-graph]` / `[F-v21-actions]` / `[F-v21-purity]` 粗码不再是 loader 的 public 诊断契约。

`load_workflow_from_md()` 仍存在，但它现在拒绝文件路径，并要求 V0.3 skill root 目录，代码在 `packages/graph-agent/src/graph_agent/core/loader.py:211` 到 `packages/graph-agent/src/graph_agent/core/loader.py:229`。这个名字带有 legacy 色彩，baseline 里不把它描述为新的 canonical compile API。

### 输入文件契约

当前编译 API 接受的文件契约是：

- 根目录必须有 `GRAPH.md`，见 `packages/graph-agent/src/graph_agent/core/loader.py:266` 到 `packages/graph-agent/src/graph_agent/core/loader.py:268`。
- 根目录必须有 `phases/`，见 `packages/graph-agent/src/graph_agent/core/loader.py:270` 到 `packages/graph-agent/src/graph_agent/core/loader.py:272`。
- phase 目录必须有且只能有一种 node 文件，见 `packages/graph-agent/src/graph_agent/core/loader.py:285` 到 `packages/graph-agent/src/graph_agent/core/loader.py:292`。
- IO schema 引用必须指向 skill root 内的 `.json` 文件，见 `packages/graph-agent/src/graph_agent/core/loader.py:861` 到 `packages/graph-agent/src/graph_agent/core/loader.py:884`。

### 与 execution-runtime 的交接 API

编译模块不执行图。它把 `CompiledSkill` 交给 `assemble_graph(compiled, chat_model=...)`，后者定义在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:55`。所以本 feature 的 API 边界是 "目录 -> CompiledSkill"，runtime feature 的 API 边界是 "CompiledSkill -> compiled LangGraph -> invoke"。交接点详见 [execution-runtime/baseline.md#api](../execution-runtime/baseline.md#api)。

## Data Model / State

### `CompiledSkill`

`CompiledSkill` 是编译阶段最重要的 state。它不是持久化 schema，而是运行时内存对象。字段定义在 `packages/graph-agent/src/graph_agent/core/loader.py:65` 到 `packages/graph-agent/src/graph_agent/core/loader.py:75`：

- `raw` 保存原始 graph/io/phases 信息，供后续 runtime 取 output schema 等数据。
- `manifest` 是 `GraphManifest`。
- `nodes` 是 `PhaseDocument` 列表。
- `actions` 和 `tools` 是 registry。
- `subagents_by_phase` 记录每个父 SKILL phase 的 subagent metadata。
- `phase_tokens` 保存 `GRAPH.md` 中 `<phase />` 标签 token 的位置信息。

`PhaseDocument` 定义在 `packages/graph-agent/src/graph_agent/core/loader.py:53` 到 `packages/graph-agent/src/graph_agent/core/loader.py:62`。它把单个 phase 的 `phase_name`、文件路径、mode、frontmatter、raw blocks 和 typed AST 放在一起。

`CompiledSubagent` 定义在 `packages/graph-agent/src/graph_agent/core/loader.py:78` 到 `packages/graph-agent/src/graph_agent/core/loader.py:89`。它保存父 phase、subagent 名称、路径、描述、root、input schema、Pydantic input model 和 expected schema。这个结构会在 runtime 注入 `call_subagent_<name>` 工具时使用。

### cache snapshot 现状和 P1-1/P2-2

audit P1-1 指出 cache hit 会丢 `subagents_by_phase` 和 `phase_tokens`，问题位置见 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:221`。当前代码符合这个描述：`_dehydrate_compiled_skill()` 只写 `raw`、`manifest`、`nodes`，见 `packages/graph-agent/src/graph_agent/core/cache.py:84` 到 `packages/graph-agent/src/graph_agent/core/cache.py:99`；`_rehydrate_compiled_skill()` 只恢复 `actions` 和 `tools`，并构造 `CompiledSkill(raw, manifest, nodes, actions, tools)`，见 `packages/graph-agent/src/graph_agent/core/cache.py:102` 到 `packages/graph-agent/src/graph_agent/core/cache.py:126`。它没有传 `subagents_by_phase` 或 `phase_tokens`，所以 dataclass 默认空值会生效。

audit P2-2 指出 cache 默认写 HOME 且写失败没有降级，问题位置见 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:434`。当前 `get_cache_dir()` 和 `save_to_cache()` 的实现分别在 `packages/graph-agent/src/graph_agent/core/cache.py:18` 与 `packages/graph-agent/src/graph_agent/core/cache.py:45`，确实没有把写失败包装成 no-cache 行为。

### A7/A8 的当前覆盖边界

audit A7 说 agent phase / subagent `SKILL.md` 头部缺少必须声明的 phase-level `io` dict，位置是 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:769`。当前 `SkillNodeAST` 只要求 `system_prompt`、`exit_contract`、`tools`、`subagents`，见 `packages/graph-agent/src/graph_agent/core/manifest.py:83` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:90`；没有 phase-level `io` 字段。因此当下实现只有根级 `io/inputs.json` / `io/outputs.json`，没有每个 agent phase 自己的输入输出字典。

audit A8 说需要图级 IO 数据流校验，位置是 `docs.backup-2026-05-20/engine/graph-agent-audit/graph-agent-audit-merged-authoritative__by-codex-2026-05-20.md:812`。当前实现有拓扑校验、JSON Schema 合法性校验、LOGIC action 写键校验，但没有检查 "每个 phase required input 是否由 initial inputs 或 upstream outputs 提供" 这种整图数据流。代码证据是 `_validate_graph_topology()` 只处理 phase id/src/depends_on/环/孤岛/src 路径，见 `packages/graph-agent/src/graph_agent/core/loader.py:730` 到 `packages/graph-agent/src/graph_agent/core/loader.py:771`；`_validate_io_schema()` 只校验 schema 文件自身，见 `packages/graph-agent/src/graph_agent/core/loader.py:874` 到 `packages/graph-agent/src/graph_agent/core/loader.py:900`。

### 当前编译阶段不会执行的事情

为了避免把 baseline 写成理想设计，需要明确当前编译阶段不做以下事情。

第一，编译阶段不运行 action/tool。它会 import Python 模块并校验函数签名，见 `_load_python_module()` 在 `packages/graph-agent/src/graph_agent/core/loader.py:530` 到 `packages/graph-agent/src/graph_agent/core/loader.py:542`，以及 `_validate_action_signature()` 在 `packages/graph-agent/src/graph_agent/core/loader.py:553` 到 `packages/graph-agent/src/graph_agent/core/loader.py:570`。但是业务 action 的实际调用发生在 LOGIC node runtime，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:127` 到 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:136`。

第二，编译阶段不解析真实 LLM provider。`compile_skill()` 接受 `chat_model` 只是为了稳定公开签名，实际会删除它，见 `packages/graph-agent/src/graph_agent/core/compiler.py:43` 到 `packages/graph-agent/src/graph_agent/core/compiler.py:52`。真实模型是否存在，是 execution runtime 的问题。

第三，编译阶段不保证 runtime input 合法。`_validate_io_schema()` 只证明 `io/inputs.json` 是合法 JSON Schema，见 `packages/graph-agent/src/graph_agent/core/loader.py:896` 到 `packages/graph-agent/src/graph_agent/core/loader.py:900`。真正调用时 `_run_v030_skill_dict()` 仍然把 `**inputs` 原样放进 `data`，见 `packages/graph-agent/src/graph_agent/core/runner.py:503` 到 `packages/graph-agent/src/graph_agent/core/runner.py:508`。

第四，编译阶段不建立 per-phase input/output mapping。`GraphPhaseRef` 只有 `id`、`src`、`depends_on`，见 `packages/graph-agent/src/graph_agent/core/manifest.py:16` 到 `packages/graph-agent/src/graph_agent/core/manifest.py:23`。它没有 "input from phase X output Y" 的字段。

### 读代码时的主路径提示

如果读者想从代码理解编译，推荐按这个顺序跳：

1. 从 `compile_skill()` 看 cache 包装，位置是 `packages/graph-agent/src/graph_agent/core/compiler.py:40`。
2. 跳到 `SkillLoader.compile_skill()` 看主流程，位置是 `packages/graph-agent/src/graph_agent/core/loader.py:142`。
3. 看 `_guard_v21_root()` 理解目录硬约束，位置是 `packages/graph-agent/src/graph_agent/core/loader.py:256`。
4. 看 `_validate_graph_topology()` 理解图结构校验，位置是 `packages/graph-agent/src/graph_agent/core/loader.py:730`。
5. 看 `_validate_io_schema()` 理解 IO schema 只做文件/schema 合法性校验，位置是 `packages/graph-agent/src/graph_agent/core/loader.py:874`。
6. 看 `_compile_subagent_metadata()` 和 `_inject_subagent_tools()` 理解 subagent 如何变成动态 tool，位置分别是 `packages/graph-agent/src/graph_agent/core/loader.py:340` 和 `packages/graph-agent/src/graph_agent/core/loader.py:387`。
7. 最后看 `cache.py` 的 dehydrate/rehydrate，位置分别是 `packages/graph-agent/src/graph_agent/core/cache.py:84` 和 `packages/graph-agent/src/graph_agent/core/cache.py:102`，这里能直接看到 P1-1 的现状。
