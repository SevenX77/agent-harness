# Round 29 Design Draft v7 — Complexity Gate & C901 Refactoring

## §0 Prerequisite (worktree state)
- **主控已 file-scoped restore 4 round-28 contract gate test files** (`git restore --staged --worktree`): `test_public_api_contract.py` / `test_contract_hash_lock.py` / `test_round28_contract_manifests.py` / `test_round28_invariant_guards.py`。a1 实施前 `ls packages/graph-agent/tests/` verify 4 文件存在; `git status --short` verify 不在 D-staged 区。
- 实施期间禁止 `git stash` / `git checkout HEAD -- .` / `git reset --hard` (覆盖 4 gate files 会再退化, 之前迭代踩过坑)。

## §1 立项目标 (Charter)
- **根本诉求**：提升引擎世界级成熟度（对标 LangGraph/Temporal）。基于过往历史：PR γ2 (`825860a` round-13 State/IO Isolation) 以及 P0-2 系列：P0-2a (`6bacef9` Python CI matrix) / P0-2b (`daf7382` refactor 1) / P0-2c (`aa60b84` refactor 2 / `9847e9d` reduce safe C901 hotspots) 均已完整合入，完成了底层重构，现正式实施“筑地板”的进阶治理任务。(PR-8 在 stage 已合, wc/contract-docs 暂未含, 故 13 violations 中 `legacy_context_from_state` + `_wrap_tool_for_langchain` 仍存待 round-29 重构)。
- **任务范围**：针对核心包 `packages/graph-agent` 开启 Ruff `C901` 复杂度门（`max-complexity=10`），并处理目前现存的 13 处业务 src violations 与 2 处 scripts/ 验证工具 violations（共 15 处）。

## §2 分批重构策略
**Base policy**: 本 round base on `wc/contract-docs` (HEAD `2f8290c`, 含 PR-8 + P0-2 + round-15..28 完整上游 + round-28 contract)。按 `[staged_merge_workflow]` 完成后 `--no-ff` 进 stage。

推荐**分批重构（分 2 批）**，按测试覆盖率、业务核心度和复杂度切分，以控制回归风险：
- **Batch 1 (核心调度)**：
  - **4 核心调度**：`execute` (44), `run` (25), `on_event` (14), `resume` (13)。
  以上高频/核心接口复杂度大，需优先拆解并确保回归安全。
- **Batch 2 (Helper 函数 Test-first 原地重构)**：
  - **9 Helper 函数**：`parse_output_example`, `_build_type_runtime`, `_parse_block_data`, `_coerce_value`, `_validate_cross_references`, `_normalise_type`, `_violation_for_call`, `legacy_context_from_state`, `_wrap_tool_for_langchain`。
  先补测试，再原地重构（工作量中，风险极低）。

*附：完整 13 src 函数名单及复杂度见 §5。*

## §3 复杂度门配置
考虑到全仓启 C901 会命中 apps/studio/backend 及 skills 等 30+ 处，为控制 Round 29 scope，采用以下**选项 A（推荐）**的 per-package 策略（根配置保持不变）：

```toml
# packages/graph-agent/pyproject.toml 新增段
[tool.ruff]
extend = "../../pyproject.toml"

[tool.ruff.lint]
extend-select = ["C901"]

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.ruff.lint.per-file-ignores]
"scripts/**" = ["C901"]
```

## §4 黄金原则保障
重构 13 个 src 函数必须保 65 API / 92 错误码 / 33 事件 / 53 H2 章节 / FROZEN docs SHA hash 一个不漏。重构后必须跑 round-28 contract validator 保持 GREEN 守门。具体 guard 清单如下：
- `tests/test_public_api_contract.py` (含 `EXPECTED_CONTRACT_SYMBOLS` + `EXPECTED_SIGNATURES` + `EXPECTED_FIELD_CONTRACTS` + `EXPECTED_CALLBACK_PROTOCOL_METHODS` + `EXPECTED_EXCEPTION_MRO`) (65 public symbols field-level)
- `tests/test_contract_hash_lock.py` (53 H2 + FROZEN docs SHA-256 (14 docs/engine/mvp0/skill-spec/* + 4 contract docs SHA-256))
- `tests/test_round28_contract_manifests.py::test_primary_owner_unique_per_error_code_and_event` (92 错误码 + 33 事件 single primary owner (验 `R28_PRIMARY_OWNER_DUPLICATE`/`MISSING`))
- `tests/test_round28_invariant_guards.py` (R28 5 机制 guard: prompt_template_8_slots / middleware_order / tool_sandbox / blackboard_mapping / f_v3_error_metadata_shape)
- **全套 pytest GREEN** (整体 regression 防护)
- `tests/callbacks/*` (验证 callback emit ordering 顺序一致性)
- `tests/core/test_state*` (WorkflowState lifecycle 及 deepcopy 隔离机制有效性)
- `tests/core/test_error_payload_contract.py` (ErrorPayload 路径不漂移)

Callback Protocol 含 `on_event` / `on_nudge` / `on_working_memory_update` / `on_dead_end_pruned` / `on_compaction` / `on_ambiguity_report` 等 method, 重构 helper 不可改 method signature。

## §5 测试策略 (Test-First)
重构前，必须掌握**完整 13 src 全名单**：

- **src 13 函数 (4 核心 + 9 helper) — test-first + 重构**：
  - **4 核心（Refactor-first）**：
    1. `execute` (core/phase_nodes/llm_phase_node.py:80) - C901: 44
    2. `run` (core/harness.py:435) - C901: 25 (**`GraphAgentHarness` framework entrypoint, signature 必稳 (即使不在 65 API). 重构 helper 必保 `run(...)` / `resume(...)` 调用契约不变**)
    3. `on_event` (callbacks/base.py:139) - C901: 14 (**属 Callback Protocol (65 API), signature 必稳: `(self, event: GraphAgentEvent) -> None` 必稳 — 重构内部分发为辅助函数, signature 不动, 否则 `test_public_api_contract.py::EXPECTED_CALLBACK_PROTOCOL_METHODS` red gatekeeper 触发**)
    4. `resume` (core/harness.py:949) - C901: 13 (**`GraphAgentHarness` framework entrypoint, signature 必稳 (即使不在 65 API). 重构 helper 必保 `run(...)` / `resume(...)` 调用契约不变**)
  - **9 Helper 函数（Test-first）**：
    5. `parse_output_example` (tools/dynamic_schema.py:71) - C901: 12
    6. `_build_type_runtime` (tools/dynamic_schema.py:316) - C901: 12
    7. `_parse_block_data` (tools/md_to_json.py:332) - C901: 12
    8. `_coerce_value` (cognitive/md2json.py:88) - C901: 11
    9. `_validate_cross_references` (config/llm_config.py:359) - C901: 11
    10. `_normalise_type` (core/_predict_internal/stub.py:115) - C901: 11
    11. `_violation_for_call` (core/purity.py:130) - C901: 11
    12. `legacy_context_from_state` (core/state.py:167) - C901: 21
    13. `_wrap_tool_for_langchain` (core/tool_wrapper.py:102) - C901: 24

**Chars 写计划**: a1 已写 8 chars 锁 9 helper (`parse_output_example`, `_build_type_runtime`, `_parse_block_data`, `_coerce_value`, `_validate_cross_references`, `_normalise_type`, `_violation_for_call`, `on_event`, `legacy_context_from_state`); 4 framework entrypoint (`run`, `resume`, `execute`, `_wrap_tool_for_langchain`) 已有 e2e + integration tests 锁, 不写新 chars。

*注：`scripts/validate_round28_manifest.py` 2 violations (`_validate_features` :130 / `main` :246) 通过 §3 per-file-ignore 豁免, 不重构 (一次性 contract validator)。*

## §6 风险 / Open Question / 分歧
1. **`execute` 重构之深水区保障**：由于 `execute` 的复杂度高达 44，拆解 State Machine 时必须建立**具体保障**：
   - (a) 提取 helper 前后，确保 **callback emit 的发送顺序** 严格一致。
   - (b) **WorkflowState lifecycle verify**：必须验证流转中各个内部 State 生命周期的不变量未被打破。
   - (c) **state dict deepcopy 防御**：警惕隐式闭包引用与被调用方篡改，通过 copy/冻结上下文等手段切断副作用。

## §7 Golden Principle 4 维度验证表
强化 4 维度验证保障：
- **65 public API symbols 不漂**：`test_public_api_contract.py` 守门。含 13 Callback Protocol method 签名: `on_phase_start` / `on_phase_end` / `on_llm_call` / `on_tool_call` / `on_validation_fail` / `on_retry` / `on_finish_task` / `on_nudge` / `on_working_memory_update` / `on_dead_end_pruned` / `on_compaction` / `on_ambiguity_report` / `on_event`。`on_event` 重构 signature 必不漂。
- **92 错误码 + 33 事件 single primary owner**：`test_round28_contract_manifests.py` 守门。13 helper 重构不动错误码 / 事件 owner。
- **53 H2 章节 + 14 FROZEN docs SHA-256**：`test_contract_hash_lock.py` 守门。13 helper 重构不动 `docs/engine/mvp0/skill-spec/*`。
- **R28 5 机制 invariant**：`test_round28_invariant_guards.py` 守门。13 helper 重构不破 5 机制。