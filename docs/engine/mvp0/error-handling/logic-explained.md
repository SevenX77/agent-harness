# ErrorPayload Logic Explained

本文翻译当前代码里的错误码与 `ErrorPayload` 机制。它不是目标态设计稿，而是对
`graph_agent.core.exceptions`、`graph_agent.core.error_registry` 和相关调用点的字段级说明。

## 核心对象

`ErrorPayload` 定义在 `packages/graph-agent/src/graph_agent/core/exceptions.py`。它是框架错误跨边界传递时的结构化载体，字段分两组。

必填语义字段有 5 个：

- `code`: 规范错误码，例如 `[F-v3-graph-phase-cycle]`。Pydantic 层要求非空字符串。构造后会到 `ERROR_REGISTRY` 查表；查不到直接 `ValueError`。
- `level`: 错误等级，目前由 registry 自动补齐，典型值是 `FATAL` 或 `WARN`。调用方可以传入，但通常不传。
- `stage`: 生命周期阶段，类型是 `tuple[str, ...]`。单阶段如 `("编译期",)`，双阶段如 `("编译期", "运行期")`。
- `message`: 人可读错误信息。Pydantic 层要求非空字符串。它描述现场，不替代 `code`。
- `doc_link`: 指向 11-spec 或相关规范章节的相对链接，由 registry 自动补齐。

推荐上下文字段有 4 个：

- `skill_id`: 出错 skill 的业务 id。
- `phase_id`: 出错 phase 的 id。
- `field_path`: 出错字段路径，例如 `io.inputs`。
- `source_path`: 出错源文件路径。`make_error_payload()` 接受 `str | Path`，内部统一转成字符串。

`ErrorPayload` 的 `model_validator(mode="after")` 做两件事。第一，用 `code` 查 `ERROR_REGISTRY`，未知码立即拒绝。第二，将 `level`、`stage`、`doc_link` 从 registry 自动补齐；补齐后仍为空，也会报 `ValueError("incomplete error metadata ...")`。这让调用点只需要提供 `code`、`message` 和可选上下文，避免每个 raise 站点重复写等级和文档链接。

`make_error_payload()` 是调用点的短路径。它只包装 `ErrorPayload(...)`，没有额外容错；因此未知 code、空 message、registry 元数据缺失都会沿着 `ErrorPayload` 的校验失败。

## Error Registry

`ERROR_REGISTRY` 定义在 `packages/graph-agent/src/graph_agent/core/error_registry.py`，当前有 92 个 core 错误码。每项是 `ErrorCodeMetadata`：

- `code`: 与 dict key 相同的 bracketed code。
- `level`: 规范等级。
- `stage`: 阶段 tuple。
- `doc_link`: 规范链接。

`stage` 用 tuple 是因为有些错误确实跨多个生命周期阶段。当前测试明确保护双阶段码，例如：

- `[F-v3-resource-reference-path-invalid]`: `("编译期", "运行期")`
- `[F-v3-resource-example-path-invalid]`: `("编译期", "运行期")`
- `[F-v3-skill-not-registered]`: `("编译期", "装配期")`
- `[F-v3-cognitive-output-schema-invalid]`: `("装配期", "装配前")`

registry 与 `docs/engine/skill-spec/11-error-code-spec.md` 的一致性由红灯 suite 守住：

- `test_error_registry_matches_error_code_spec_key_set` 要求 registry key-set 与 11-spec 中的 92 个 `[F-v3-...]` code 完全相等。
- `test_error_registry_entries_have_complete_nonempty_metadata` 要求每项 `code`、`level`、`stage`、`doc_link` 都非空。
- `test_error_registry_preserves_multi_stage_codes` 钉住多阶段 tuple，不允许被压扁成字符串或单阶段。

## GraphAgentError.payload

`GraphAgentError.__init__()` 的当前实现是混合机制：

```python
self.payload = payload or _payload_from_message(message)
```

首选路径是调用方显式传入 `payload=make_error_payload(...)`。PR F 已把主要框架 raise 站点迁到这个形式。这样 code 是参数，不靠解析 message，`message` 只负责解释现场。

兼容路径是 `_payload_from_message(message)`。它用正则 `\[F-v3-[a-z0-9-]+\]` 从 message 中找第一个 bracketed code，然后分三种行为：

- 找不到 `[F-v3-...]` token: 返回 `None`。这保留了无码内部异常的合法状态，不强迫所有内部异常都有 spec code。
- 找到 token 且 code 在 `ERROR_REGISTRY`: 构造 `ErrorPayload(code=code, message=message)`，由 registry 自动补齐元数据。
- 找到 token 但不是 core registry code: 默认 fail loud，抛 `ValueError("unknown graph_agent error code in message: ...")`。这是 must-fix 后的行为，用来堵住拼错码或未注册码静默变成 `payload=None` 的后门。

还有一个明确的外部域例外：`[F-v3-gateway-*]`。gateway 包的异常继承 public family `ModelProviderError`，也就是继承 `GraphAgentError`，但 gateway 的三个码在 gateway 文档和包内维护，不在 core `ERROR_REGISTRY`。所以 `_payload_from_message()` 对 `[F-v3-gateway-*]` 返回 `None`，不把它们当 core 未注册码处理。gateway 异常仍保留自己的 `code` 和 `context` 字段。

## Public Exception Families

PR-A 将 SDK 顶层 public exception catalog 从 leaf-heavy API 浓缩为 5 个 public class：`GraphAgentError`、`GraphCompileError`、`GraphExecutionError`、`ModelProviderError`、`ResourceNotFoundError`。

这不是删除内部错误颗粒度。内部实现仍可以 raise leaf class，例如 `SkillLoadError`、`SkillCompilationError`、`SkillResolutionError`、`ExecutionError`、`TraceWriteError` 和 gateway leaf errors。变化是这些 leaf 现在只作为 implementation detail 存在；外部调用方按 family catch，然后用 `ErrorPayload.code` 和 `ERROR_REGISTRY` 元数据区分具体错误现场。

当前 family 边界如下：

- `GraphCompileError`: loader/parser/schema/contract/template/compile 类错误。内部 leaf 如 `SkillLoadError` 和 `SkillCompilationError` 是这个 family。
- `GraphExecutionError`: runtime phase/state/tool/persistence/trace/artifact/retry/fatal execution 类错误。内部 leaf 如 `ExecutionError` 和 `GraphAgentFatalError` 是这个 family。
- `ModelProviderError`: gateway/provider/role/model/fallback 类错误。`GatewayError` 继承这个 family。
- `ResourceNotFoundError`: skill id、resource ref、workspace path 等定位失败。Engine `SkillResolutionError` 是这个 family；Studio resolver 可以直接 raise `ResourceNotFoundError`，并用 `[F-v3-skill-not-registered]` 或 `[F-v3-resolver-path-invalid]` 保留颗粒度。

因此文档和调用方不应写“对外 catch `SkillLoadError` / `SkillResolutionError`”。正确边界是“内部可 raise leaf；对外 catch family；用 `payload.code` 分支”。

这个实现不是纯粹的最终理想形态。设计意图是新站点用 explicit `payload=`，但为了不一次性重写所有历史路径，当前代码保留 message 解析兼容层；must-fix 的重点是让“长得像 core code 但未注册”的情况响亮失败，而不是静默生成 `payload=None`。

## 失败边界

直接构造 `ErrorPayload(code="[F-v3-not-in-spec]", message="...")` 会失败，因为 registry 查不到 code。

构造 `GraphAgentFatalError("[F-v3-typo-not-registered] typo")` 也会失败。它走 `_payload_from_message()`，发现 message 里有 core 形态 code，但 registry 查不到，于是抛 `ValueError`。`test_graph_agent_error_rejects_unknown_embedded_code` 钉住这个契约。

构造 `GraphAgentError("plain internal error")` 不会失败，payload 为 `None`。这类无码异常可以作为内部错误使用，但跨用户边界或框架契约边界时应优先改成 explicit payload。

## JSON 边界

`ErrorPayload.model_dump_json()` 会把 Python tuple 序列化成 JSON array。测试 `test_error_payload_json_boundary_shape_uses_required_keys_and_stage_array` 钉住跨边界形态：

- 必须包含 `code`、`level`、`stage`、`message`、`doc_link`。
- `stage` 在 JSON 中是数组，例如 `["编译期"]`。

这意味着 Python 内部用 tuple 表示不可变阶段序列，对外 JSON 使用普通数组。

## 粗码退役

PR F 退役了旧粗码 `[F-v3-route]`、`[F-v3-io]`、`[F-v3-graph]`、`[F-v3-actions]`、`[F-v3-purity]`。当前 loader 和相关 helper 改为传 11-spec 细码，例如 graph schema、phase、IO、action、purity 各自的具体 code。

`test_engine_source_has_no_coarse_error_code_literals` 扫描 `packages/graph-agent/src/graph_agent/**/*.py`，要求这些粗码在 engine source 中 0 命中。这个测试只看源码字面量，不替代 registry/spec key-set 校验。

## Loader 与调用点模式

loader 侧有 code-aware helper，例如 `_fatal()`、`_actions_fatal()`、`_purity_fatal()`。它们把路径、行号和清理后的 message 拼成 detail，然后用 `make_error_payload(code, detail, source_path=path)` 构造 payload。部分 helper 有默认 code，但调用点可以传更细的 code；这保留了局部封装，同时让最终 payload 落到 11-spec code。

运行期调用点也遵循同一模式。例如 action 返回非 dict 时，`graph_assembler` 抛 `GraphAgentFatalError`，payload code 是 `[F-v3-logic-action-return-invalid]`。builtin reference/example 读取失败时也显式传 payload。

must-fix 后，`core/builtin_subagents/reference_reader.py` 的 timeout 站点不再只写 `GraphAgentFatalError("[F-v3-reference-reader-failed] timeout")`，而是显式：

```python
detail = "[F-v3-reference-reader-failed] timeout"
raise GraphAgentFatalError(
    detail,
    payload=make_error_payload("[F-v3-reference-reader-failed]", detail),
) from exc
```

这里 message 里仍保留 code 方便日志和人读，但 payload 不依赖 message 解析。

## Finish Task 的两个错误形态

`packages/graph-agent/src/graph_agent/cognitive/finish_task.py` 有两个不同语义，使用不同 code。

第一类是装配前/装配期的 `output_schema` 本身非法。`_check_output_schema()` 发现 JSON Schema 不合法、不像对象 schema、`type` 不是 object、`properties` 不是 dict 时，会抛 `GraphAgentFatalError`，payload code 是 `[F-v3-cognitive-output-schema-invalid]`。这个码是 PR F 收口期补入 registry 的错误码。

第二类是 LLM 最终 markdown 解析或校验失败，需要以结构化 dict 回传给 LLM 重试机制。`_structured_error()` 返回：

```python
{
    "ok": False,
    "error": {
        "code": "[F-v3-agent-output-schema-invalid]",
        "kind": ...,
        "attempts": ...,
        "validation_errors": ...,
        "markdown_excerpt": ...,
    },
}
```

这个路径不是抛异常，而是保留工具返回契约；它复用运行期 `[F-v3-agent-output-schema-invalid]`，因为语义是 agent 输出不匹配 schema。

## 实施期补充的两个码

`[F-v3-logic-action-purity-violation]` 用于 action 纯度检查失败。loader 的 `_purity_fatal()` 和相关调用点使用它，阶段是编译期，doc link 指向 LOGIC action 契约。它替代旧粗码 `[F-v3-purity]`。

`[F-v3-cognitive-output-schema-invalid]` 用于 `finish_task` 的 `output_schema` 结构非法。阶段是 `("装配期", "装配前")`，doc link 指向 Cognitive 动态装配插槽解析。它只覆盖 schema 本身非法；LLM 输出内容不匹配 schema 的重试反馈仍使用 `[F-v3-agent-output-schema-invalid]`。

## PR-4 递归编译错误码

PR-4 增加了两个 compile domain 错误码，专门覆盖 subgraph/subagent 递归编译链路。它们都由 `SkillLoader.compile_skill()` 构造 `SkillLoadError` 时显式传入 `payload=make_error_payload(...)`，不会依赖 message 解析。

`[F-v3-compile-recursion-cycle]` 表示当前 skill root 已经出现在 `_loading_stack` 中。典型现场是 A 的 SUBGRAPH 或 subagent 指向 B，B 又通过 SUBGRAPH 或 subagent 指回 A。字段语义如下：

- `code`: `[F-v3-compile-recursion-cycle]`
- `level`: `FATAL`
- `stage`: `("编译期",)`
- `doc_link`: `./11-error-code-spec.md#compile-domain`
- `message`: 当前实现会写出 `recursive skill compilation cycle detected at <root_key>`，其中 `<root_key>` 是 `str(root.resolve())` 后的绝对路径。
- `source_path`: 当前正在尝试进入的 root path。

排查时先看 message 里的 root key，再沿 `target_skill` 查最近的 SUBGRAPH phase 或 Agent `subagents[]` 声明。修复方式通常是打断 skill 间的循环引用，或把共享能力抽成第三个不会反向引用父图的 skill。

`[F-v3-compile-depth-exceeded]` 表示递归编译父链路已经达到安全上限。当前 loader 在 push 当前 root 之前检查 `len(_loading_stack) >= 20`，因此不会让第 21 层继续展开。字段语义如下：

- `code`: `[F-v3-compile-depth-exceeded]`
- `level`: `FATAL`
- `stage`: `("编译期",)`
- `doc_link`: `./11-error-code-spec.md#compile-domain`
- `message`: 当前实现会写出 `recursive skill compilation depth exceeded at <root_key>`。
- `source_path`: 触发上限时准备进入的 root path。

这个码不一定说明存在环，也可能只是链路太深。排查时按 `target_skill` 从入口向下数层级，优先合并中间转发 skill，或把重复引用改成同层共享引用。`_compilation_cache` 会去重同一个 root 的重复编译，但不会降低真实嵌套深度。

## 测试守卫

当前机制由 `packages/graph-agent/tests/core/test_error_payload_contract.py` 重点守护：

- registry key-set 必须等于 11-spec 的 92 个 code。
- registry 每项元数据必须完整。
- 两个递归编译 code 必须存在，level 为 `FATAL`，stage 包含 `编译期`，且 doc link 非空。
- `ErrorPayload` 未知 code 必须拒绝。
- `GraphAgentError` message 中的未知 core code 必须 fail loud。
- concrete `GraphAgentFatalError` 能暴露可序列化 payload。
- loader、runtime、builtin tool 的代表性失败路径必须带预期 payload code。
- engine source 中退役粗码必须 0 命中。
- JSON 边界必须包含 required keys，且 `stage` 序列化为数组。
