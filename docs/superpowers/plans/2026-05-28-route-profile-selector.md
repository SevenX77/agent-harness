# Route Profile Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first backend slice that lets LLM role resolution map user reasoning preferences to verified provider methods and request mappers.

**Architecture:** Keep `ProviderRoute` model-level and add typed `VerifiedProfile` data under the route. The registry resolver selects a verified profile per route from `RoleRouteEntry.runtime_settings`, writes the selected method/mapper into `ResolvedRoute`, and rejects required reasoning when no verified thinking profile exists.

**Tech Stack:** Python, Pydantic v2, pytest, `packages/graph-agent-gateway`.

---

### Task 1: Schema And Resolver Profile Selection

**Files:**
- Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py`
- Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py`
- Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/registry/__init__.py`
- Test: `packages/graph-agent-gateway/tests/test_registry_profile_selector.py`

- [ ] **Step 1: Write failing schema and resolver tests**

Create `packages/graph-agent-gateway/tests/test_registry_profile_selector.py` with tests for:

- Claude Opus adaptive thinking preferred selects `anthropic_messages` + `anthropic_thinking_adaptive`.
- Manual-thinking Claude selects `anthropic_thinking_manual_budget` and carries default budget.
- Required thinking rejects routes with only text profiles.
- OpenAI prefers Responses over Chat when both satisfy text.
- Required OpenAI reasoning does not fallback to Chat text-only.
- Ark Chat-only route selects `ark_chat`.
- DeepSeek image+thinking selects `deepseek_anthropic_messages`.

- [ ] **Step 2: Verify tests fail before implementation**

Run:

```bash
PYTHONPATH=packages/graph-agent-gateway/src pytest packages/graph-agent-gateway/tests/test_registry_profile_selector.py -q
```

Expected: import/attribute failures for missing `VerifiedProfile` or missing selected profile fields.

- [ ] **Step 3: Implement minimal schema**

Add:

- `ProfileCapability`
- `VerifiedProfile`
- selected profile fields on `ResolvedRoute`
- `verified_profiles` on `ProviderRoute`

- [ ] **Step 4: Implement minimal resolver selection**

In `resolve_role`, select the profile that satisfies `runtime_settings.reasoning.enabled` and optional input modality metadata, ordered by profile default/rank. Raise `RegistryResolutionError` when required reasoning is requested but no thinking/reasoning profile is verified.

- [ ] **Step 5: Verify green**

Run:

```bash
PYTHONPATH=packages/graph-agent-gateway/src pytest packages/graph-agent-gateway/tests/test_registry_profile_selector.py -q
PYTHONPATH=packages/graph-agent-gateway/src pytest packages/graph-agent-gateway/tests/test_registry_resolver.py packages/graph-agent-gateway/tests/test_registry_schema.py -q
```

Expected: all selected tests pass.

### Task 2: Runtime Dispatch Receives Selected Profile Method

**Files:**
- Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py`
- Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py`
- Test: `packages/graph-agent-gateway/tests/test_gateway_integration.py`

- [ ] **Step 1: Write the failing gateway dispatch test**

Extend `test_gateway_passes_effective_runtime_settings_to_client_manager` so its `ResolvedRoute`
contains `selected_profile_id`, `call_method_id`, and `request_mapper_id`, then assert the fake
client manager receives `call_method_id` and `request_mapper_id` in `dispatch_provider_call`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=packages/graph-agent-gateway/src pytest packages/graph-agent-gateway/tests/test_gateway_integration.py::test_gateway_passes_effective_runtime_settings_to_client_manager -q
```

Expected: FAIL because dispatch kwargs do not include the selected method/mapper fields.

- [ ] **Step 3: Write minimal implementation**

Pass `candidate.call_method_id` and `candidate.request_mapper_id` from `GatewayChatModel` into
`LLMClientManager.dispatch_provider_call`, add the keyword parameters to the public method and the
private `_dispatch_provider_call` method.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=packages/graph-agent-gateway/src pytest packages/graph-agent-gateway/tests/test_gateway_integration.py::test_gateway_passes_effective_runtime_settings_to_client_manager -q
```

Expected: PASS.

### Task 5: Role Materializer Writes Reasoning Intent Into Runtime Settings

**Files:**
- Modify: `apps/studio/backend/app/services/llm_role_materializer.py`
- Test: `apps/studio/backend/tests/routers/test_llm_role_materializer_api.py`

- [ ] **Step 1: Write the failing materializer assertion**

When a role or model group has `thinking: "required"` and the route has verified
`thinking_protocol`, assert the generated `fallback_chain` entry contains
`runtime_settings.reasoning.enabled == true`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=apps/studio/backend:packages/graph-agent-gateway/src pytest apps/studio/backend/tests/routers/test_llm_role_materializer_api.py::test_get_role_v3_rematerializes_report_from_current_route_capabilities -q
```

Expected: FAIL because the materializer currently checks capability but does not write the
reasoning runtime setting.

- [ ] **Step 3: Write minimal implementation**

In `_apply_intent`, when effective thinking intent is `required` and capability is verified true,
write `entry_report["resolved_settings"]["reasoning"]["enabled"] = True`. Do the same for
`preferred` only when the route capability is verified true. Leave preferred unsupported as a
downgraded no-thinking fallback.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=apps/studio/backend:packages/graph-agent-gateway/src pytest apps/studio/backend/tests/routers/test_llm_role_materializer_api.py::test_get_role_v3_rematerializes_report_from_current_route_capabilities -q
```

Expected: PASS.

### Task 4: OpenAI Call Method Selects Responses API

**Files:**
- Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py`
- Test: `packages/graph-agent-gateway/tests/test_client_manager_runtime_policy.py`

- [ ] **Step 1: Write the failing Responses dispatch test**

Add a test proving a route call with `call_method_id="openai_responses"` invokes
`client.responses.create` with `max_output_tokens`, not `client.chat.completions.create`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=packages/graph-agent-gateway/src pytest packages/graph-agent-gateway/tests/test_client_manager_runtime_policy.py::test_openai_call_method_responses_uses_responses_api -q
```

Expected: FAIL because OpenAI-compatible dispatch still ignores `call_method_id` and only uses Chat Completions.

- [ ] **Step 3: Write minimal implementation**

When `call_method_id == "openai_responses"`, dispatch to a new `_call_openai_responses` helper.
Map normalized runtime settings to Responses fields: `max_output_tokens`, `temperature`, optional
`top_p`, optional `reasoning.effort`, and optional structured output.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=packages/graph-agent-gateway/src pytest packages/graph-agent-gateway/tests/test_client_manager_runtime_policy.py::test_openai_call_method_responses_uses_responses_api -q
```

Expected: PASS.

### Task 3: Anthropic Request Mapper Controls Thinking Payload

**Files:**
- Modify: `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py`
- Test: `packages/graph-agent-gateway/tests/test_client_manager_runtime_policy.py`

- [ ] **Step 1: Write the failing mapper test**

Add a test proving `request_mapper_id="anthropic_thinking_adaptive"` sends
`thinking: {"type": "adaptive"}` even when the model name is not in the hard-coded adaptive
allow-list. This ensures route profiles, not model-name guessing, control the provider payload.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=packages/graph-agent-gateway/src pytest packages/graph-agent-gateway/tests/test_client_manager_runtime_policy.py::test_anthropic_request_mapper_forces_adaptive_thinking_payload -q
```

Expected: FAIL because `_call_anthropic_compatible` does not yet accept or honor `request_mapper_id`.

- [ ] **Step 3: Write minimal implementation**

Pass `request_mapper_id` into `_call_anthropic_compatible`. If it is
`anthropic_thinking_adaptive`, send adaptive thinking directly. If it is
`anthropic_thinking_manual_budget`, send manual budget thinking directly. Keep the old model-name
heuristic path when no mapper ID is selected.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=packages/graph-agent-gateway/src pytest packages/graph-agent-gateway/tests/test_client_manager_runtime_policy.py::test_anthropic_request_mapper_forces_adaptive_thinking_payload -q
```

Expected: PASS.
