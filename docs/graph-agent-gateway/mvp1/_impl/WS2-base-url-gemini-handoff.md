---
handoff_id: WS-2-base-url-gemini-implementation
target_agent: Gemini
status: ready_for_implementation
created: 2026-06-06
source_task: ./WS2-base-url.md
kiro_tasks: ../../../../../.kiro/specs/graph-agent-gateway-mvp1/tasks.md
reviewer: Codex
---

# WS-2 base_url 保存时归一化 — Gemini 实施任务书

## 0. 当前状态

契约门已过。测试是合同，不要削弱测试来适配实现。

WS-1 已在当前工作区提供 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/base_url.py:canonicalize_base_url`。WS-2 只 import 这个 helper，不复制 URL 规则，不改 WS-1 文件。

完成实现后，向 Codex 报告修改文件、测试结果、mypy 结果和任何 deferred。Codex 会做审核；不要把“测试绿”写成“终审通过”。

## 1. 必读

先读并确认这些文件的现状，再写代码：

- `AGENTS.md`
- `docs/development/task-spec-standard.md`
- `docs/graph-agent-gateway/mvp1/_impl/WS2-base-url.md`
- `docs/graph-agent-gateway/mvp1/03-orch-credentials-endpoints/mvp1-alignment.md` 的 §F3 / §F5 / base_url 归一化契约
- `docs/graph-agent-gateway/mvp1/03-orch-credentials-endpoints/baseline.md`
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/base_url.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py`
- `apps/studio/backend/app/services/llm_credentials.py`
- `apps/studio/backend/app/services/llm_import_drafts.py`，只读审计，除非 Codex/PM 后续把它加入 owns_files

## 2. 可改文件

只改这些文件：

- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py`
- `apps/studio/backend/app/services/llm_credentials.py`
- `packages/graph-agent-gateway/tests/test_registry_storage_base_url.py`
- `apps/studio/backend/tests/services/test_llm_base_url_canonicalization.py`
- `docs/deferred-items.md`，仅在发现 secondary write entrance 不能在本轮 owns_files 内接入时登记

禁止改：

- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/base_url.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/provider_profiles.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/models.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py`
- 任何 predict_context 相关文件

不要 `git add .`。如需 stage，只按文件名 stage 自己改的文件。

## 3. 已过契约门的测试

这些测试应保持语义不变：

- `packages/graph-agent-gateway/tests/test_registry_storage_base_url.py::test_credential_fingerprint_uses_protocol_canonical_base_url`
- `apps/studio/backend/tests/services/test_llm_base_url_canonicalization.py::test_upsert_endpoints_persists_protocol_canonical_base_urls`
- `apps/studio/backend/tests/services/test_llm_base_url_canonicalization.py::test_upserted_canonical_base_url_is_what_resolver_reads`

如果测试因 import 路径或 fixture 形状需要机械修正，可以做最小修正并报告；不许删除关键断言。

## 4. 实现要求

1. `registry/storage.py`
   - 让 `compute_credential_fingerprint(endpoint, secret=None)` 使用 protocol-canonical base_url。
   - `_normalize_base_url` 可改成接收 `protocol`，内部调用 `canonicalize_base_url(value, protocol)`。
   - 保持 fingerprint 其他输入不变。

2. `llm_credentials.py`
   - `upsert_endpoints` 保存 endpoint 前，把 `incoming.base_url` 改成 `canonicalize_base_url(incoming.base_url, incoming.protocol)`。
   - 保留 `_preserved_secret`、provider_kind、rate_limit_bucket、atomic save、`0600` 等既有行为。
   - `_v3_payload_to_v4` 如果在同文件内可干净接入，也用同一个 helper。

3. secondary write entrance
   - `llm_import_drafts.py:apply_draft` 当前不在 WS-2 owns_files。只审计，不擅自改。
   - 如果它仍会写 raw base_url，请在 `docs/deferred-items.md` 增加一条明确 deferred：import draft apply base_url canonicalization 待独立 owns_files 放行。

## 5. 验证命令

必须运行并报告：

```bash
uv run pytest packages/graph-agent-gateway/tests/test_registry_storage_base_url.py -q
uv run pytest apps/studio/backend/tests/services/test_llm_base_url_canonicalization.py -q
uv run pytest packages/graph-agent-gateway/tests -q
uv run mypy packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py apps/studio/backend/app/services/llm_credentials.py
```

如果 Studio backend 全套太大，至少跑上述 service 测试；如果失败不是本任务范围，保留原始错误并报告，不要顺手修无关模块。

## 6. 回报格式

完成后按这个格式回报 Codex：

```text
WS-2 implementation complete / blocked

Changed files:
- ...

Verification:
- command -> result

Deferred:
- none / exact item

Notes for Codex review:
- ...
```

Codex 审核重点：是否复用 WS-1 helper、是否覆盖 F3/F5、是否没有第二份 URL 规则、是否没有越权改文件、是否诚实登记 secondary write entrance。
