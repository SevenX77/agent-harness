# WS3 PR-5 Tasks: ModuleSandbox sys.modules 清理与 LLMClientManager 生命周期收敛

## Cutover Discipline

本 PR 按 design 执行，但实施时必须收紧两个工程交叉点：
- `ModuleSandbox` 的 `sys.modules` 写入是临时加载期能力，`exec_module` 与 `_rebuild_pydantic_models` 完成或失败后都必须清理；这是 [BREAKING] 行为切换。
- `LLMClientManager._clients` 是进程级共享缓存，所有 `_clients` 读写链路都必须由同一把 class-level lock 覆盖，并新增 `close_all()` 释放 OpenAI/Anthropic 底层 HTTP 连接池。
- `hoist_to` 活机制在 V0.3.0 不存在，本 PR 纯 NO-OP、无需测试；inline schema 已在现状代码中解决，本 PR 不改对应生产逻辑，只允许加 regression-lock 绿测试。

实施必须 tests-first：
- 先写诚实红灯测试并真实运行确认失败原因指向当前缺陷；再改生产代码转绿。
- 不得把 src 与 tests 混在同一任务里一并写。Green 任务对 test 的触碰仅限红灯转绿验证、[BREAKING] cutover 同步断言更新，以及本 PR 明确允许的 schema regression-lock 绿测试。
- 不允许 skip/xfail，不允许用 `collect_ignore`、弱断言、过度 mock 或绕开真实代码路径来凑绿。
- [BREAKING] `sys.modules` 切换必须一次性更新测试契约与迁移说明；不得保留沙盒模块常驻 `sys.modules` 的兼容分支。

已核对的当前断点：
- `packages/graph-agent/src/graph_agent/core/module_sandbox.py` 在 `_load_module` 中写 `sys.modules[spec.name] = module`，在 `_load_from_file` 中写 `sys.modules[sandbox_name] = module`，两处都没有 `finally` 清理。
- `packages/graph-agent/tests/core/test_module_sandbox.py` 当前有测试断言本次加载后存在 `_graph_agent_sandbox_*_schemas` key；PR-5 需要把这个旧契约反向切换为加载成功/失败后不残留。
- `packages/graph-agent/src/graph_agent/tools/md_to_json.py` 的 `_resolve_schema_from_path` 会从 `sys.modules` 反查动态 schema；这是 [BREAKING] 迁移风险，必须通过受影响路径测试确认不再依赖沙盒残留。
- `packages/graph-agent/src/graph_agent/models/llm_client_manager.py` 中 `_clients.get(...)` 与 `_clients[...] = ...` 未加锁，也没有 `close_all()`。
- `rg -n "\.hoist_to\s*=" packages/graph-agent/src` 当前无匹配；V0.3.0 无活的 `hoist_to` 机制。残留 `phase.hoist_to` 引用位于无调用方的 `skill_validator.py` 死代码，建议 PR-6 治理清理。
- `loader.py` 的 `_validate_inline_io_schema` 已包含 `isinstance(schema, dict)` 与 `Draft202012Validator.check_schema(schema)`。

## Tasks

### 1. Red: LLMClientManager 并发初始化与 close_all 红灯

Files:
- `packages/graph-agent/tests/models/test_llm_client_manager.py`

Steps:
- 新增并发初始化测试，针对同一 OpenAI-compatible provider 同时触发 `_get_openai_client(...)`，必须使用确定性注入制造 check-then-act 交错，不使用裸 barrier 或概率性竞态。
- 推荐注入机制：patch SDK client factory 为受控 fake factory，factory 内记录调用计数；第一次构造进入后设置 `entered_event` 并等待 `release_event`，测试线程在 `entered_event` 后启动第二个调用，确认第二个调用已越过无锁的 `_clients.get(...)` 窗口后再释放。无锁实现应必然构造两次；加锁后第二个调用必须等待第一轮写入并复用缓存。
- 可选等价机制：factory 内使用 `threading.Event` + 计数器或受控短延迟，但必须能证明两线程必然在当前无锁 check-then-act 窗口交错；不得依赖调度概率。
- 断言所有线程拿到同一个 client 对象，且底层 client 构造只发生一次。
- 为 Anthropic-compatible provider 增加等价覆盖，或以参数化形式覆盖 OpenAI 与 Anthropic 两条 `_clients` 写入链路。
- 新增 `close_all()` 红灯测试：预置多个带 `close()` 的 fake client 到 `_clients`，调用 `LLMClientManager.close_all()`，断言每个 client 的 `close()` 被调用一次且 `_clients` 被清空。
- 新增 `close_all()` 空缓存幂等测试，确认空 `_clients` 调用不抛异常。

Acceptance:
- 在不改生产代码时，并发测试应确定性红灯，失败原因应体现重复构造或返回非同一对象；不得通过串行执行、裸 sleep 或调度运气得到假绿/假红。
- 在不改生产代码时，`close_all()` 测试应因方法缺失红灯。
- 不 mock 掉 `_clients` 读写本身；测试必须覆盖真实 class-level 缓存路径。

### 2. Red: ModuleSandbox sys.modules 无残留红灯

Files:
- `packages/graph-agent/tests/core/test_module_sandbox.py`
- `packages/graph-agent/tests/core/**` 如需新增受影响路径测试文件

Steps:
- 将现有 `test_import_class_does_not_write_public_module_to_sys_modules` 的旧断言反向切换：加载成功后既不能留下 public key，也不能留下本次加载对应的 `_graph_agent_sandbox_*_<module>` namespaced key。
- 新增失败路径测试：构造 `model_rebuild()` 会失败的 Pydantic forward-ref 模块，断言加载抛错后本次沙盒 key 仍被清理。
- 新增同名模块隔离测试：两个不同 `tmp_path` 下都提供 `schemas.py`，内容定义同名类但字段/默认值不同；分别用不同 `ModuleSandbox(search_paths=[...])` 加载并断言类行为互不污染，且 `sys.modules` 中没有任一加载留下的 public key 或 sandbox key。
- 保留 forward-ref 成功测试：`from __future__ import annotations` + `Literal[...]` 的模型加载后 `model_validate(...)` 仍成功，证明清理发生在同步 `_rebuild_pydantic_models` 之后，不破坏合法 Pydantic 使用。
- 增加或更新覆盖 `md_to_json` / schema path 解析受影响路径的测试，确认生产调用不依赖 `ModuleSandbox` 残留的 `_graph_agent_sandbox_*` key。

Acceptance:
- 在不改生产代码时，成功路径无残留测试应红灯，因为当前会留下 `_graph_agent_sandbox_*` key。
- 在不改生产代码时，失败路径无残留测试应红灯，因为当前 `model_rebuild` 异常会跳过清理。
- forward-ref 测试必须保持绿或在实现后转绿；不能用禁用 `_rebuild_pydantic_models` 换取 sys.modules 清洁。

### 3. Green: LLMClientManager 锁与生命周期钩子

Files:
- `packages/graph-agent/src/graph_agent/models/llm_client_manager.py`
- `packages/graph-agent/tests/models/test_llm_client_manager.py`

Steps:
- 引入 `import threading`，并在类上定义 `_lock: ClassVar[threading.Lock] = threading.Lock()`。
- 在 `_get_openai_client(...)` 中用同一把 lock 覆盖 `_clients.get(cache_key)`、client 构造、`_clients[cache_key] = client` 与 `_init_usage_stats(provider_code)` 的完整 check-then-create 链路。
- 在 `_get_anthropic_client(...)` 中做同样处理；不得只锁写入或只锁构造后赋值。
- 新增 `@classmethod def close_all(cls) -> None`，在 lock 内遍历当前 `_clients`，对有 `close` 属性且 callable 的 client 调用 `close()`，随后 `clear()`。
- `close_all()` 应释放 OpenAI/Anthropic SDK client 自身；这些 SDK client 会转发关闭到底层 httpx client。不要只关闭局部 `httpx.Client` 变量，因为缓存持有的是 SDK client。
- 保持现有 `_get_*_client` 调用签名不变。

Acceptance:
- 任务 1 的并发初始化与 close_all 红灯转绿。
- 现有 provider cache、timeout override、usage stats 测试继续通过。
- `rg -n "_lock|close_all|with cls\._lock|_clients" packages/graph-agent/src/graph_agent/models/llm_client_manager.py` 能看到所有 `_clients` 读写链路受锁保护。

### 4. Green [BREAKING]: ModuleSandbox 临时注册 try/finally 清理

Files:
- `packages/graph-agent/src/graph_agent/core/module_sandbox.py`
- `packages/graph-agent/tests/core/test_module_sandbox.py`
- `packages/graph-agent/tests/core/**` 如任务 2 增加受影响路径测试

Steps:
- 在 `_load_module(...)` 的 importlib fallback 路径中，用 `try...finally` 包裹：
  - `sys.modules[spec.name] = module`
  - `spec.loader.exec_module(module)`
  - `_rebuild_pydantic_models(module, spec.name)`
  - `finally: sys.modules.pop(spec.name, None)`
- 在 `_load_from_file(...)` 中用同样结构包裹 `sys.modules[sandbox_name] = module`、`exec_module`、`_rebuild_pydantic_models`，并在 `finally` 中 `sys.modules.pop(sandbox_name, None)`。
- 清理必须覆盖 `exec_module` 抛错和 `_rebuild_pydantic_models` 抛错两条失败路径。
- 保留 `self._module_cache[module_path] = module` 的行为：沙盒实例内部仍可缓存已加载 module；只是不能再借助全局 `sys.modules` 常驻。
- 更新相关注释，明确 `sys.modules` 注册只在同步 exec/rebuild 窗口内存在。

Acceptance:
- 任务 2 的 sys.modules 无残留、同名模块隔离、失败路径清理与 forward-ref 成功测试全部转绿。
- [BREAKING] 旧测试不得继续断言 `_graph_agent_sandbox_*` key 常驻。
- `rg -n "sys\.modules\[[^]]+\] = module|sys\.modules\.pop" packages/graph-agent/src/graph_agent/core/module_sandbox.py packages/graph-agent/tests/core/test_module_sandbox.py` 显示写入与清理成对出现。

### 5. NO-OP: hoist_to 活机制不存在，不改 src、不写测试

Files:
- No files expected.

Steps:
- 不新增 hoist_to regression-lock 测试。V0.3.0 无活的 `hoist_to` 机制，没有真实 validator + hoist_to 路径可锁；为此写测试只能 mock 一个不存在的机制，属于假测试。
- 不修改 `packages/graph-agent/src/**` 中的 hoist_to 逻辑。
- 保留 grep gate 作为 scope 证明即可：`.hoist_to =` 零匹配。
- `skill_validator.py` 中残留的 `phase.hoist_to` 引用属于无调用方死代码，建议 PR-6 单独治理清理；PR-5 不处理。

Acceptance:
- `rg -n "\.hoist_to\s*=" packages/graph-agent/src` 无匹配。
- PR-5 diff 不包含 hoist_to src/test 改动。

### 6. Regression-Lock [Green]: inline schema 已校验，不改 src

Files:
- `packages/graph-agent/tests/core/**`

Steps:
- 可选新增或确认已有 regression-lock 绿测试：非 dict inline schema 在加载阶段 fail-loud；非法 JSON Schema 通过 `Draft202012Validator.check_schema` 路径 fail-loud。
- 本任务不得修改 `loader.py` 的 `_validate_inline_io_schema` 生产逻辑，除非测试揭示与现有 `isinstance` / `check_schema` 事实不一致。

Acceptance:
- `rg -n "def _validate_inline_io_schema|isinstance\(schema, dict\)|Draft202012Validator\.check_schema" packages/graph-agent/src/graph_agent/core/loader.py` 能定位到现有强校验。
- regression-lock 测试通过，且没有新增 skip/xfail。

### 7. Scope Guard: 保持 PR-5 边界

Files:
- Production changes limited to:
  - `packages/graph-agent/src/graph_agent/core/module_sandbox.py`
  - `packages/graph-agent/src/graph_agent/models/llm_client_manager.py`
- Tests limited to relevant `packages/graph-agent/tests/**`

Steps:
- 不修改 Studio、Tauri、frontend、runner startup、cache、graph assembler、compiler 等非 PR-5 范围文件。
- 不修改 `.kiro/specs/.../design.md`、`research.md`、`requirements.md`，除非主控另行要求。
- 不引入新的公共必填参数；`close_all()` 是新增可选生命周期 API。
- 不派任务给别人，不在任务执行中依赖外部手工清理真实用户环境。
- 不使用清空全局真实环境作为测试手段；涉及 `sys.modules` 的测试只清理本测试创建的 key。

Acceptance:
- `git diff --name-only` 只出现本 PR 范围内的 src/test/spec tasks 文件。
- `rg -n "collect_ignore|xfail|skip\(" packages/graph-agent/tests` 没有因本 PR 新增的规避项。

### 8. Final Verification: 诚实绿与 grep gate

Files:
- No additional files expected.

Commands:
- `uv run pytest packages/graph-agent/tests/models/test_llm_client_manager.py`
- `uv run pytest packages/graph-agent/tests/core/test_module_sandbox.py`
- `uv run pytest packages/graph-agent/tests/core`
- `uv run pytest packages/graph-agent/tests/models`
- `rg -n "_lock|close_all|with cls\._lock|_clients" packages/graph-agent/src/graph_agent/models/llm_client_manager.py`
- `rg -n "sys\.modules\[[^]]+\] = module|sys\.modules\.pop|_graph_agent_sandbox_" packages/graph-agent/src/graph_agent/core/module_sandbox.py packages/graph-agent/tests/core/test_module_sandbox.py`
- `rg -n "\.hoist_to\s*=" packages/graph-agent/src`
- `rg -n "def _validate_inline_io_schema|isinstance\(schema, dict\)|Draft202012Validator\.check_schema" packages/graph-agent/src/graph_agent/core/loader.py`
- `rg -n "collect_ignore|xfail|skip\(" packages/graph-agent/tests`

Acceptance:
- 任务 1 与任务 2 的红灯均已转绿。
- `ModuleSandbox` 成功/失败加载后不留下本次 public key 或 sandbox key，但 Pydantic forward-ref 模型仍可 `model_validate`。
- `LLMClientManager` 并发首次初始化只创建一个 client，`close_all()` 关闭所有缓存 client 并清空缓存。
- `hoist_to` 为纯 NO-OP，无 src/test 改动；schema 仅有 regression-lock 绿测试或现有绿证明，无对应生产代码改动。
- 全部新增/更新测试不依赖 skip/xfail/collect_ignore 或弱断言凑绿。
