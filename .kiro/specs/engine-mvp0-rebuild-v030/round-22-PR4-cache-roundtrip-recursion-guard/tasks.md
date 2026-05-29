# WS3 PR-4 Tasks: Cache Roundtrip 忠实复水与递归编译防护

## Cutover Discipline

本 PR 按 design v2 执行，聚焦 V0.3.0 编译期缓存与递归编译链路：
- 修复缓存命中后 `subagents_by_phase`、动态 subagent tools、`phase_tokens` 丢失的问题。
- 阻断 subgraph/subagent 递归编译环与过深链路，统一落到 V3 `SkillLoadError` payload。
- 消除同一顶级编译/装配生命周期内同一 child root 的重复编译。
- 增加缓存损坏 warning，可观测但仍降级冷编译。

实施必须 tests-first：
- 先写全部诚实红灯测试，并真实运行确认失败原因指向当前缺陷。
- 再改生产代码转绿；不得把 src 与 tests 混在同一任务里一并写。Green 任务对 test 的触碰仅限红灯转绿验证与 [BREAKING] cutover 同步断言更新（如 `== 92`），不得在 green 阶段新写隐藏断言绕过 tests-first。
- 不允许 skip/xfail，不允许用 `collect_ignore`、弱断言或 mock 掩盖真实缺陷。
- [BREAKING] 项必须同步测试与契约文档，按 SOP-05 一次性切换，不保留旧缓存兼容路径。

已核对的当前断点：
- `core/cache.py` 的 snapshot 只含 `raw`、`manifest`、`nodes`，`compute_cache_key` 未带 `"format": "v2"`，缓存损坏时静默 `return None`。
- `core/loader.py` 的 `CompiledSubagent.input_model` 仍参与 dataclass compare；递归编译调用未传 `_loading_stack` / `_compilation_cache`。
- `core/loader.py` 的冷编译路径会调用 `_inject_subagent_tools(tools, subagents_by_phase)`，但 cache rehydrate 路径当前没有恢复 subagents，也没有重放 tool 注入。
- `core/graph_assembler.py` 的 `_build_subgraph_node` 与 `_subagent_runtime_map` 会重新 `SkillLoader(validate_context_writes=False).compile_skill(...)`，当前不受递归 guard 与同图缓存保护。
- `core/error_registry.py`、`docs/engine/skill-spec/11-error-code-spec.md`、`tests/core/test_error_payload_contract.py` 仍按 90 个错误码契约运行。

## Tasks

### 1. Red: 缓存 round-trip 忠实复水红灯

Files:
- `packages/graph-agent/tests/core/**`

Steps:
- 新增缓存 round-trip 测试，构造一个含 `subagents` 声明的最小 V0.3 skill root，并通过 resolver 指向 child skill root。
- 使用公开 `graph_agent.core.compiler.compile_skill(root, cache=True, skill_resolver=resolver)` 连续编译同一 root 两次，确保第二次走磁盘 cache hit。
- 断言冷编译与缓存命中的对象满足：
  - `hit.subagents_by_phase` 非空，且 `hit.subagents_by_phase == cold.subagents_by_phase`；该片段判等依赖后续 [BREAKING] 任务为 `CompiledSubagent.input_model` 标记 `compare=False`。
  - `hit.tools` 中按工具 id 断言仍包含 `call_subagent_<name>` 动态工具，证明 `_inject_subagent_tools` 已在复水后重放；不要依赖 `ToolRegistry` 或 `ToolDef` 对象整体判等。
  - `hit.phase_tokens` 非空，且某个 token 的 `attr_spans[...]` 仍是 `PhaseAttributeSpan` 对象，不是普通 dict。
- 不要断言整对象 `cold == hit`；`CompiledSkill.actions`、`tools` 及动态函数/模型对象存在身份差异，整对象判等不是本 PR 的正确性契约。
- 测试必须清理或隔离 cache 目录，可 monkeypatch `graph_agent.core.cache.get_cache_dir` 指向 `tmp_path`，避免污染用户本地缓存。

Acceptance:
- 在不改生产代码时，该测试应红灯，失败原因应体现缓存命中后 `subagents_by_phase` / `phase_tokens` 为空、动态 tools 丢失，或 `hit.subagents_by_phase == cold.subagents_by_phase` 因 `input_model` type 对象不同而失败。
- 不新增 skip/xfail，不通过强行禁用 cache 得到假绿。

### 2. Red: 递归环检测与深度超限红灯

Files:
- `packages/graph-agent/tests/core/**`

Steps:
- 新增 A -> B -> A 或自引用 subagent/subgraph fixture，resolver 返回对应 skill root。
- 编译 A，断言抛 `SkillLoadError`，且 `exc.value.payload.code == "[F-v3-compile-recursion-cycle]"`。
- 新增深度链 fixture，构造 root0 -> root1 -> ...，链路长度超过 20。
- 按 design §2.2.3 的 push 前判定口径断言：进入某个 child 前若 `len(_loading_stack) >= 20`，抛 `SkillLoadError`，且 `payload.code == "[F-v3-compile-depth-exceeded]"`。
- 测试应覆盖 loader 编译期的 subagent/subgraph 递归路径，不依赖 Python 原生 `RecursionError`。

Acceptance:
- 在不改生产代码时，环测试应因 `RecursionError`、无结构化 payload，或未知错误码失败。
- 深度测试应因无深度 guard 或无 `[F-v3-compile-depth-exceeded]` payload 失败。
- 不把断言写成只匹配 message 字符串；必须检查 payload code。

### 3. Red: 错误码注册契约红灯

Files:
- `packages/graph-agent/tests/core/test_error_payload_contract.py`

Steps:
- 将 registry/spec key set 数量断言从 `90` 改为 `92`，覆盖 `test_error_registry_matches_error_code_spec_key_set` 与 `test_error_registry_entries_have_complete_nonempty_metadata` 中的数量断言。
- 新增或扩展断言，要求以下 code 存在且 metadata 完整：
  - `[F-v3-compile-recursion-cycle]`
  - `[F-v3-compile-depth-exceeded]`
- 断言 level 为 `FATAL`，stage 包含 `编译期`，`doc_link` 非空并指向 11-spec 中的相关章节。

Acceptance:
- 在不改 `error_registry.py` 与 `11-error-code-spec.md` 时，该测试必须红灯。
- 红灯原因应是 registry/spec key set 不匹配或新 code 缺失，不允许先放宽 unknown-code 校验。

### 4. Red: assemble 路径递归 guard 与同图去冗红灯

Files:
- `packages/graph-agent/tests/core/**`

Steps:
- 新增 assemble 路径递归测试，覆盖 `graph_assembler.py` 中 `_build_subgraph_node` 与 `_subagent_runtime_map` 触发的 `SkillLoader(...).compile_skill(...)`。
- 构造装配期 A -> B -> A 或等价循环，调用 `assemble_graph(compiled_a, skill_resolver=resolver)` 或执行触发 child assemble 的最小 graph，断言得到 `SkillLoadError` 且 payload code 为 `[F-v3-compile-recursion-cycle]`，而不是 `RecursionError`。
- 新增同图去冗测试：根图中 3 次引用同一个 child root。
- 统计口径必须收紧到同一 child root：可 monkeypatch `SkillLoader.compile_skill` 或 parser/read 层，只统计目标 child root 的真实冷编译次数。
- 断言在一次顶级编译/装配生命周期内，该 child root 真实编译次数为 1。

Acceptance:
- 在不改生产代码时，assemble 环测试应红灯，表现为未受 guard 覆盖或落到 `RecursionError`。
- 同图去冗测试应红灯，表现为同一 child root 被重复编译。
- 不使用笼统的 `parse_markdown_parts` 总调用次数等脆弱断言；父图和其他文件解析不计入目标 child root 次数。

### 5. Green [BREAKING]: cache schema v2 与忠实 snapshot/rehydrate

Files:
- `packages/graph-agent/src/graph_agent/core/cache.py`
- `packages/graph-agent/src/graph_agent/core/loader.py`
- `packages/graph-agent/tests/core/**`

Steps:
- [BREAKING] 在 `compute_cache_key` payload 中加入 `"format": "v2"`，强制旧缓存失效；不写旧 snapshot 兼容迁移。
- [BREAKING] 在 `CompiledSubagent.input_model` 字段上使用 `field(compare=False)`，使 `hit.subagents_by_phase == cold.subagents_by_phase` 这类片段级 dataclass equality 可达；不要承诺 `CompiledSkill` 整对象 equality。
- 在 `_dehydrate_compiled_skill` 中加入：
  - `phase_tokens`，并显式拆解嵌套 `PhaseAttributeSpan`。
  - `subagents_by_phase`，但剔除不可 JSON 序列化的 `input_model`。
  - `CompiledSubagent.root` 以字符串保存。
- 在 `_rehydrate_compiled_skill` 中严格复原：
  - `PhaseTokenInfo` 与嵌套 `PhaseAttributeSpan`，不得留下普通 dict。
  - `CompiledSubagent.root` 复原为 `Path`。
  - `input_model` 通过 `build_subagent_input_model(_subagent_input_model_name(parent_phase_id, name), input_schema)` 重建。
  - `expected_schema` 保持与冷编译一致；若重算，必须与 helper 输出稳定一致。
- 在 rehydrate 发现 actions/tools 后，使用 `_inject_subagent_tools(tools, subagents_by_phase)` 重放动态 subagent tool 注入。

Acceptance:
- 任务 1 的缓存 round-trip 测试转绿。
- `hit.subagents_by_phase == cold.subagents_by_phase` 成立；`hit.tools` 按工具 id 可见 `call_subagent_<name>`；`phase_tokens.attr_spans` 对象契约不丢失。
- `rg "\"format\": \"v2\"|format.*v2" packages/graph-agent/src/graph_agent/core/cache.py` 能定位到 cache key 版本切换。

### 6. Green [BREAKING]: 错误码注册与 11-spec 落盘

Files:
- `packages/graph-agent/src/graph_agent/core/error_registry.py`
- `docs/engine/skill-spec/11-error-code-spec.md`
- `packages/graph-agent/tests/core/test_error_payload_contract.py`

Steps:
- [BREAKING] 在 `ERROR_REGISTRY` 注册：
  - `[F-v3-compile-recursion-cycle]`
  - `[F-v3-compile-depth-exceeded]`
- 为两个 code 写完整 metadata：`level="FATAL"`，stage 至少为 `("编译期",)`，`doc_link` 指向 11-spec 的稳定锚点。
- 在 `11-error-code-spec.md` 增加两个 code 的说明，保持 registry/spec key set 完全一致。
- 将 `test_error_payload_contract.py` 中的数量断言固定为 `92`，并保留 unknown code 拒绝测试。

Acceptance:
- 任务 3 的错误码契约测试转绿。
- `ErrorPayload(code="[F-v3-compile-recursion-cycle]", message="...")` 与 depth code 均可构造并自动补齐 metadata。
- registry 与 11-spec key set 一致，不通过删除或放宽 contract test 凑绿。

### 7. Green: loader 递归 guard 与同图编译缓存

Files:
- `packages/graph-agent/src/graph_agent/core/loader.py`
- `packages/graph-agent/src/graph_agent/core/compiler.py`
- `packages/graph-agent/tests/core/**`

前置依赖: task 6 已注册 `[F-v3-compile-recursion-cycle]` 与 `[F-v3-compile-depth-exceeded]` 两个新错误码。

Steps:
- 为 `SkillLoader.compile_skill` 增加内部关键字参数：
  - `_loading_stack: tuple[str, ...] = ()`
  - `_compilation_cache: dict[str, CompiledSkill] | None = None`
- 这些参数仅供内部递归链路透传；公开 `graph_agent.core.compiler.compile_skill(...)` API 不新增公开必填参数。
- 在进入编译前统一计算 `root_key = str(root.resolve())`。
- 环检测：若 `root_key in _loading_stack`，抛 `SkillLoadError`，payload code 为 `[F-v3-compile-recursion-cycle]`。
- 深度上限：push 当前 root 前若 `len(_loading_stack) >= 20`，抛 `SkillLoadError`，payload code 为 `[F-v3-compile-depth-exceeded]`。
- 同图缓存：若 `root_key` 已在 `_compilation_cache` 中，直接返回该 `CompiledSkill` 引用。
- 冷编译成功后，将当前 `root_key` 写入 `_compilation_cache`。
- 所有 loader 内部递归调用点，包括 `_validate_subgraph_io_contracts` 与 `_compile_subagent_metadata`，必须透传更新后的 stack/cache，并保留 `validate_context_writes=False` 的既有语义。
- 顶级 `compiler.compile_skill(cache=True)` 的磁盘 cache 与本任务的内存 `_compilation_cache` 是两层不同机制；内存 cache 只覆盖一次顶级编译生命周期，不落盘。

Acceptance:
- 任务 2 的 loader 环检测与深度超限测试转绿。
- 任务 4 中同图去冗测试的 loader 部分转绿。
- 现有 `compile_skill(..., cache=False|True, skill_resolver=...)` 调用方无需传新参数。

### 8. Green: graph_assembler 递归状态透传

Files:
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- `packages/graph-agent/tests/core/**`

前置依赖: task 6 已注册 `[F-v3-compile-recursion-cycle]` 与 `[F-v3-compile-depth-exceeded]` 两个新错误码。

Steps:
- 为 `assemble_graph` 及必要的内部 helper 增加内部递归状态参数，至少能将 `_loading_stack` 与 `_compilation_cache` 传入：
  - `_build_subgraph_node`
  - `_subagent_runtime_map`
- `graph_assembler.py` 中所有 `SkillLoader(validate_context_writes=False).compile_skill(...)` 调用必须透传同一 stack/cache。
- 子图 `assemble_graph(...)` 递归调用也必须继续传递相同状态，避免编译阶段有 guard、装配阶段又断链。
- 保持公开调用 `assemble_graph(compiled, ..., skill_resolver=resolver)` 兼容；新增参数应为内部可选参数。

Acceptance:
- 任务 4 的 assemble 路径递归 guard 测试转绿，环路抛 `SkillLoadError` 且 payload code 为 `[F-v3-compile-recursion-cycle]`。
- 同一 child root 在装配路径中只真实编译一次。
- 不改变 subgraph/subagent 运行期行为、tracing tag、callback、depth runtime guard 等非本 PR 范围语义。

### 9. Green: 缓存损坏 warning 可观测性

Files:
- `packages/graph-agent/src/graph_agent/core/cache.py`
- `packages/graph-agent/tests/core/**`

Steps:
- 在 `cache.py` 顶部增加 `logger = logging.getLogger(__name__)`。
- `load_from_cache` 捕获 `OSError`、`json.JSONDecodeError`、`KeyError`、`TypeError`、`ValueError` 时，用 `logger.warning("[Cache] Failed to load cached compiled skill %s: %s", key, exc)` 或等价信息记录 WARNING。
- 保持降级行为：warning 后仍 `return None`，由上层冷编译，不让坏 cache 使进程崩溃。
- 新增测试可 monkeypatch cache dir 写入坏 JSON，然后用 `caplog` 断言 WARNING 出现，同时编译最终成功。

Acceptance:
- 坏 cache 文件不会导致编译失败。
- `caplog` 能捕获 WARNING，且日志含 cache key 或 cache 文件上下文与异常原因。
- 不把所有 cache miss 都打 warning；只有损坏/读取异常路径记录。

### 10. Scope Guard: 保持 PR-4 边界

Files:
- No production file expected beyond tasks 5-9.
- Tests should stay under `packages/graph-agent/tests/**`.

Steps:
- 不改变 public API 的必填参数；新增递归状态参数必须是内部可选参数。
- 不修改非 PR-4 相关的 runner、md_to_json、Studio、Tauri、frontend 文件。
- 不引入新的 resolver 语义，不恢复 legacy path 字段，不修改 skill fixture 大规模结构，除非测试最小 fixture 必需。
- 不删除或弱化 `ErrorPayload` unknown-code 拒绝、registry/spec key set 对齐测试。
- 不用清空用户真实 cache 目录作为测试手段；测试必须隔离 cache dir。

Acceptance:
- `git diff --name-only` 只出现本 PR 相关 src/test/doc 文件。
- `rg "collect_ignore|xfail|skip\\(" packages/graph-agent/tests` 没有因本 PR 新增的规避项。
- `rg "RecursionError" packages/graph-agent/tests/core` 不作为 PR-4 目标行为断言。

### 11. Final Verification: 诚实绿与 grep gate

Files:
- No additional files expected.

Commands:
- `uv run pytest packages/graph-agent/tests/core/test_error_payload_contract.py`
- `uv run pytest packages/graph-agent/tests/core`
- `uv run pytest packages/graph-agent/tests`
- `rg -n "compile-recursion-cycle|compile-depth-exceeded" packages/graph-agent/src docs/engine/skill-spec packages/graph-agent/tests`
- `rg -n "\"format\": \"v2\"|format.*v2|subagents_by_phase|phase_tokens|_inject_subagent_tools" packages/graph-agent/src/graph_agent/core/cache.py packages/graph-agent/src/graph_agent/core/loader.py`
- `rg -n "SkillLoader\\(validate_context_writes=False\\)\\.compile_skill|_loading_stack|_compilation_cache" packages/graph-agent/src/graph_agent/core/loader.py packages/graph-agent/src/graph_agent/core/graph_assembler.py`

Acceptance:
- 新增红灯全部已转绿。
- 错误码 registry/spec/test 三方一致，数量为 92。
- 缓存 round-trip 覆盖 `hit.subagents_by_phase == cold.subagents_by_phase`、dynamic tools 按 id 可见、phase token nested dataclass。
- loader 与 assemble 两条递归路径均抛结构化 `SkillLoadError`，不会裸漏 `RecursionError`。
- 同一 child root 在一次顶级编译/装配生命周期内只真实编译一次。
- 全量 pytest 若执行，应为 `0 failed`；不得依赖 skip/xfail/collect_ignore 凑绿。
