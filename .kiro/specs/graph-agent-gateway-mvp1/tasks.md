---
status: Ready for Implementation
created: 2026-06-06
owner: Graph-Agent Gateway
related_design: ../../../docs/graph-agent-gateway/mvp1/_impl/WS2-base-url.md
related_requirements: ../../../docs/graph-agent-gateway/mvp1/03-orch-credentials-endpoints/mvp1-alignment.md
review_flow: Contract tests passed -> Gemini implementation -> Codex review -> baseline writeback
---

# Graph-Agent Gateway MVP1 WS-2 Tasks

> 给 agentic worker：WS-2 契约门已通过。Gemini 只负责把已批准的 RED 测试实现到 GREEN；不要削弱测试，不要抢做 Codex 的审核和 baseline 回写。

## Phase 0: 契约门

- [x] 0.1 确认 WS-2 契约测试已通过审查
  - 已批准测试覆盖保存时 base_url per-protocol canonical、credential fingerprint 等价 URL 稳定、保存后 resolver 读取同一路径。
  - 测试文件：`packages/graph-agent-gateway/tests/test_registry_storage_base_url.py`。
  - 测试文件：`apps/studio/backend/tests/services/test_llm_base_url_canonicalization.py`。
  - 当前 RED 失败原因符合预期：保存侧和 fingerprint 尚未调用 canonical helper。
  - _Requirements: 03.F3, 03.F5_

## Phase 1: Gateway storage fingerprint

- [ ] 1.1 让 credential fingerprint 使用 protocol-canonical base_url
  - 更新 registry storage 的 fingerprint 路径，让参与 hash 的 `base_url` 先按 endpoint protocol canonicalize。
  - 必须复用 `graph_agent_gateway.registry.base_url.canonicalize_base_url`，禁止复制第二份 URL 规则。
  - 除 canonical base_url 外，保持 fingerprint 其他输入不变：endpoint id、protocol、secret、credential ref、timeout、trust_env、proxy env。
  - 验证命令：`uv run pytest packages/graph-agent-gateway/tests/test_registry_storage_base_url.py -q`。
  - _Requirements: 03.F3, 03.F5_

## Phase 2: Studio credentials 保存侧 canonical

- [ ] 2.1 `upsert_endpoints` 保存 canonical base_url
  - 保存每条 incoming endpoint 前，用 `canonicalize_base_url(base_url, protocol)` 得到写入值。
  - 保持四类协议契约：anthropic-compatible 去尾 `/v1`；DeepSeek Anthropic 去 `/v1` 并补 `/anthropic`；Ark 补 `/api/v3`；OpenAI-compatible 保持 `/v1` 形状。
  - 保持既有 secret 保留、redaction placeholder、provider_kind seed/repair、rate_limit_bucket 保留、原子写和 `0600` 权限行为。
  - 验证命令：`uv run pytest apps/studio/backend/tests/services/test_llm_base_url_canonicalization.py::test_upsert_endpoints_persists_protocol_canonical_base_urls -q`。
  - _Requirements: 03.F3_

- [ ] 2.2 保证保存值等于 resolver runtime 值
  - upsert 后，credentials 文件中的 endpoint base_url 必须等于 resolver 输出的 `ResolvedRoute.base_url`。
  - 不要新增 resolver/runtime-only 归一化来掩盖保存侧没 canonical 的问题。
  - 验证命令：`uv run pytest apps/studio/backend/tests/services/test_llm_base_url_canonicalization.py::test_upserted_canonical_base_url_is_what_resolver_reads -q`。
  - _Requirements: 03.F3, 03.F5_

## Phase 3: Secondary write entrance 审计

- [ ] 3.1 审计 v3 migration 和 import draft apply 写入路径
  - v3→v4 migration 位于 `apps/studio/backend/app/services/llm_credentials.py`，如果能在同文件内干净复用同一 helper，则接入 canonical。
  - `apps/studio/backend/app/services/llm_import_drafts.py` 当前不在 WS-2 owns_files；只读审计，未经 Codex/PM 明确放行不要改。
  - 如果发现本轮不能接入的写入口仍会写 raw base_url，必须在 `docs/deferred-items.md` 登记精确 deferred，并在回报里列明。
  - F4 endpoint 拆分 + canonical endpoint_id 下沉不在本轮，已登记为 `DEF-019`；不要改 `_stable_endpoint_id`。
  - _Requirements: 03.F3_

## Phase 4: 验证与回报

- [ ] 4.1 跑 WS-2 必要验证
  - 运行 `uv run pytest packages/graph-agent-gateway/tests/test_registry_storage_base_url.py -q`。
  - 运行 `uv run pytest apps/studio/backend/tests/services/test_llm_base_url_canonicalization.py -q`。
  - 运行 `uv run pytest packages/graph-agent-gateway/tests -q`。
  - 运行改动文件 mypy：`uv run mypy packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py apps/studio/backend/app/services/llm_credentials.py`。
  - 如果有 Studio/Tauri dev session 正在运行，修改 backend Python 后按项目规则重启 Studio App；若未运行，报告“未启动 dev session，无需重启”。
  - _Requirements: 03.F3, 03.F5_

- [ ] 4.2 向 Codex 回报等待审核
  - 回报 modified files、每条验证命令和结果、是否有 deferred、是否重启 Studio App。
  - 不要 claim “终审通过”；Gemini 完成后由 Codex 审查到 WS-2 §8 硬退出全满足，再由 Codex 回写 baseline。
  - 不要 stage；如后续被要求 stage，只能按文件名 stage WS-2 owns 文件，禁止 `git add .`。
  - _Requirements: 03.F3, 03.F5_
