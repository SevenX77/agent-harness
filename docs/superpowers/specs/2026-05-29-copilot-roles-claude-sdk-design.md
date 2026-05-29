# Studio Copilot Roles and Claude SDK Runtime Design

Date: 2026-05-29
Status: Proposed

## Problem

Studio currently treats Copilot routing as a thin variant of graph-agent model
routing. That is no longer enough. A Copilot role is not only a model fallback
chain. It also chooses an agent runtime, and each runtime has its own provider
compatibility rules, environment variables, tool behavior, permission model,
and smoke-test requirements.

The immediate target is Claude Agent SDK support for two fixed Copilot roles:

- `copilot_opus_4_7`
- `copilot_deepseek_v4`

The design must also leave a clean path for future runtimes, such as a Codex SDK
runtime, without changing the user-facing role model again.

## Goals

- Add two fixed Studio Copilot role slots.
- Make each Copilot role explicitly select a Copilot SDK/runtime.
- Show the selected SDK as a badge next to the role title.
- Use SDK-specific compatibility checks when testing Copilot roles.
- Support Claude Agent SDK with Anthropic official and DeepSeek official routes.
- Make DeepSeek V4 default to Pro with no fallback.
- Keep graph-agent roles and Copilot roles visually and behaviorally separate.
- Avoid silent provider switching. Users must see when code and prompts go to
  DeepSeek instead of Anthropic.

## Non-Goals

- Do not replace graph-agent role execution.
- Do not introduce Codex SDK execution in this phase.
- Do not make OpenAI, Gemini, or Ark routes executable through Claude Agent SDK
  unless they expose an Anthropic/Claude Code compatible surface.
- Do not use model fallback for `copilot_deepseek_v4`.
- Do not run paid live smoke tests automatically in the background.

## Fixed Copilot Roles

Studio owns two fixed Copilot role slots:

```text
copilot_opus_4_7
  display_name: Opus 4.7 Copilot
  role_kind: copilot
  copilot_sdk: claude_agent_sdk
  default model: Claude Opus 4.7
  default fallback: disabled

copilot_deepseek_v4
  display_name: DeepSeek V4 Copilot
  role_kind: copilot
  copilot_sdk: claude_agent_sdk
  default model: DeepSeek V4 Pro
  default fallback: disabled
```

These role ids are system role ids. Users should not delete or rename them.
Users may edit their route selection, SDK selection, budget, tools, and runtime
settings.

`copilot_deepseek_v4` must use a Pro route by default. It must not silently
fallback to Flash. If the Pro route fails compatibility or live testing, the
role is unavailable until the user fixes the Pro route or explicitly changes the
role configuration.

For DeepSeek Pro, the Claude Agent SDK adapter should prefer the verified Pro
model id that the endpoint exposes for Claude Code compatibility. If both are
available, prefer `deepseek-v4-pro[1m]` for the agent runtime; otherwise use
`deepseek-v4-pro`. Both are Pro-class selections. Neither implies fallback to
Flash.

## Role Schema

Extend Studio role authoring with Copilot-specific fields:

```python
class RoleEntry:
    role_kind: Literal["graph_agent", "copilot"]
    display_name: str | None
    model_fallback_enabled: bool
    model_groups: list[RoleModelGroup]
    fallback_chain: list[RoleRouteEntry]
    copilot_settings: CopilotRoleSettings | None

class CopilotRoleSettings:
    slot: Literal["opus_4_7", "deepseek_v4"] | None
    sdk: Literal["claude_agent_sdk", "codex_sdk"]
    system_managed: bool
    sdk_runtime: dict[str, object]
    test_policy: CopilotTestPolicy

class CopilotTestPolicy:
    live_test_budget_usd: float
    require_text_smoke: bool
    require_read_tool_smoke: bool
    require_edit_tool_smoke: bool
    require_thinking_smoke: bool
```

`sdk_runtime` is intentionally namespaced data. The first concrete namespace is:

```python
class ClaudeAgentSdkRuntimeSettings:
    permission_mode: Literal["acceptEdits", "dontAsk", "plan", "default"]
    tools: list[str]
    allowed_tools: list[str]
    thinking: Literal["off", "adaptive", "enabled", "preferred", "required"]
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None
    max_budget_usd: float | None
    max_turns: int | None
    strict_mcp_config: bool
```

The first implementation can store `sdk_runtime` as a typed Pydantic model
inside the Studio backend and serialize it as JSON/YAML in the role file.

## UI Design

Graph-agent roles and Copilot roles should share low-level route picker
components, but they should not share the same high-level card.

Copilot role cards use this title shape:

```text
Opus 4.7 Copilot      [Claude Agent SDK]
DeepSeek V4 Copilot   [Claude Agent SDK]
```

The badge text is the selected runtime. Recommended labels:

- `Claude Agent SDK`
- `Codex SDK`

Copilot role cards expose:

- SDK selector.
- Primary route selector.
- Fallback toggle.
- SDK compatibility status.
- Agent smoke test button.
- Runtime settings for tools, permission mode, budget, thinking, and effort.

The DeepSeek V4 card default state:

- SDK: `Claude Agent SDK`
- Route: DeepSeek V4 Pro route
- Fallback: off
- Test button copy must disclose that DeepSeek API costs may be incurred.

## Runtime Request Flow

The Copilot WebSocket request should identify the fixed Copilot role:

```typescript
type CopilotWsRequestPayload = {
  user_message: string
  role_name: "copilot_opus_4_7" | "copilot_deepseek_v4"
  route_override?: string
}
```

`model_override` can remain as a temporary backwards-compatible alias for
`route_override`, but new frontend code should send `role_name`.

Backend flow:

```text
WebSocket request
  -> load active roles
  -> ensure fixed Copilot roles exist
  -> materialize selected Copilot role
  -> resolve_role(snapshot, role_name, route_override)
  -> reject route_override if it is not in the selected role fallback_chain
  -> build SDK options via selected runtime adapter
  -> run ClaudeSDKClient
  -> translate SDK messages to Copilot events
```

The resolver must materialize role model groups before resolving. A Copilot role
configured only through `model_groups` is not executable until it produces a
runtime `fallback_chain`.

## Claude Agent SDK Adapter

Introduce a boundary like:

```python
class CopilotRuntimeAdapter(Protocol):
    def supports(route: ResolvedRoute, role: RoleEntry) -> CompatibilityResult: ...
    def build_options(
        route: ResolvedRoute,
        role: RoleEntry,
        workspace_dir: Path,
    ) -> ClaudeAgentOptions: ...
```

The first adapter is `ClaudeAgentSdkAdapter`.

The adapter converts a resolved route into `ClaudeAgentOptions`. This must be a
separate unit from route resolution, because route resolution answers "which
provider model should be tried", while the adapter answers "can this SDK execute
that provider model, and with which environment variables".

### Anthropic Official

Compatible route shape:

```text
protocol: anthropic_compatible
call_method_id: anthropic_messages
base_url: https://api.anthropic.com
```

Generated options:

```python
ClaudeAgentOptions(
    model=route.provider_model_id,
    cwd=workspace_dir,
    tools=runtime.tools,
    allowed_tools=runtime.allowed_tools,
    permission_mode=runtime.permission_mode,
    env={
        "ANTHROPIC_API_KEY": api_key,
        "ANTHROPIC_BASE_URL": route.base_url,
    },
)
```

### DeepSeek Official

Compatible route shape:

```text
endpoint_id: deepseek-official
call_method_id: deepseek_anthropic_messages
base_url: https://api.deepseek.com
provider_model_id: deepseek-v4-pro[1m] or deepseek-v4-pro
```

Generated options:

```python
ClaudeAgentOptions(
    model=deepseek_pro_model_id,
    cwd=workspace_dir,
    tools=runtime.tools,
    allowed_tools=runtime.allowed_tools,
    permission_mode=runtime.permission_mode,
    env={
        "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
        "ANTHROPIC_AUTH_TOKEN": api_key,
        "ANTHROPIC_API_KEY": api_key,
        "ANTHROPIC_MODEL": deepseek_pro_model_id,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": deepseek_pro_model_id,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": deepseek_pro_model_id,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": deepseek_pro_model_id,
        "CLAUDE_CODE_SUBAGENT_MODEL": deepseek_pro_model_id,
    },
)
```

`ANTHROPIC_API_KEY` is included as a compatibility fallback. DeepSeek's Claude
Code integration documents `ANTHROPIC_AUTH_TOKEN` as the primary token variable.

### Unsupported Routes

Routes using OpenAI Chat Completions, OpenAI Responses, Google GenAI, or Ark
runtime are not Claude Agent SDK compatible by default. They may still be valid
graph-agent routes and valid raw API probe routes.

The user-facing error should say:

```text
This route can generate text, but it is not compatible with Claude Agent SDK.
Choose an Anthropic-compatible route or change the Copilot SDK.
```

## Thinking, Tokens, and Effort

Claude Agent SDK does not require a thinking-capable model. A non-thinking text
smoke test is enough to prove basic Claude SDK connectivity. DeepSeek V4 Flash
already passed a text smoke test without requiring thinking.

Hard compatibility requirements:

- Anthropic/Claude Code compatible request surface.
- Correct base URL and authentication env variables.
- The selected model id is accepted by the SDK runtime.
- The model can answer through the Claude Code agent loop.
- The model can handle the tool protocol required by the selected tool policy.

Not hard requirements:

- Thinking support.
- Reasoning effort support.
- 1M context support.
- A specific maximum output token value.

Recommended defaults:

```text
copilot_opus_4_7
  thinking: adaptive
  effort: high
  tools: Read, Write, Edit, Bash
  allowed_tools: Read, Write, Edit, Bash
  max_turns: unset for normal chat; 1 for smoke tests

copilot_deepseek_v4
  thinking: off or preferred
  effort: medium
  tools: Read, Write, Edit, Bash after edit smoke passes
  allowed_tools: Read initially; expand after compatibility passes
  max_turns: unset for normal chat; 1 for smoke tests
```

For smoke tests, do not require thinking unless the role's `thinking` setting is
`required`. If `thinking` is `preferred`, run the core text/tool tests first and
record a warning if thinking is not available.

Minimum practical token guidance:

- Basic Copilot chat: 4k output tokens is acceptable.
- Code editing and review: 8k or higher is preferred.
- Repo-scale repair: 128k context or higher is preferred.

These are quality thresholds, not SDK compatibility gates.

## Compatibility Test Design

There are two separate test families.

### Provider API Test

This is the existing route/provider probe. It proves that an endpoint and model
can produce a minimal generation through a provider API method.

It does not prove Claude Agent SDK compatibility.

### Copilot Agent Compatibility Test

This test runs through the selected Copilot SDK. For Claude Agent SDK, it should
use the same adapter that production Copilot chat uses.

Route-level endpoint:

```text
POST /api/llm/routes/{route_id}/agent-compatibility-test
```

Role-level endpoint:

```text
POST /api/llm/copilot-roles/{role_name}/agent-compatibility-test
```

Request:

```json
{
  "sdk": "claude_agent_sdk",
  "phases": ["text", "read_tool", "edit_tool", "thinking"],
  "budget_usd": 0.25
}
```

Response:

```json
{
  "status": "ok",
  "sdk": "claude_agent_sdk",
  "route_id": "deepseek-official:deepseek-v4-pro",
  "model": "deepseek-v4-pro",
  "phases": [
    {
      "phase": "text",
      "status": "ok",
      "assistant_text": "OK",
      "result_subtype": "success",
      "estimated_cost_usd": 0.05
    }
  ],
  "warnings": [],
  "errors": []
}
```

Phase behavior:

```text
text
  tools: []
  prompt: Reply with exactly OK and nothing else.

read_tool
  temp cwd contains smoke.txt
  tools: ["Read"]
  allowed_tools: ["Read"]
  prompt: Read smoke.txt and reply with exactly its content.

edit_tool
  temp cwd contains smoke.txt
  tools: ["Read", "Edit"]
  allowed_tools: ["Read", "Edit"]
  prompt: Replace smoke.txt content with OK_EDITED.
  verification: Studio reads temp file after SDK exits.

thinking
  only required when role thinking is required
  otherwise report warning or skipped.
```

The smoke test must not print secrets. It must use a temporary workspace under
`/private/tmp` or the platform temp directory. It must not use the user's active
skill directory.

Default live-test budgets:

```text
Opus 4.7 role: 0.25 USD
DeepSeek V4 Pro role: 0.25 USD
```

The UI must show that the test can incur provider API costs before running it.

## Migration

On startup or registry load, ensure the two fixed roles exist.

If a fixed role is missing, create it with an empty route selection and a setup
required state. Do not silently invent credentials.

If a legacy `copilot_chat` role exists:

- Keep it in storage for one compatibility release.
- Do not show it as one of the two fixed Copilot role cards.
- If `copilot_opus_4_7` is unconfigured, offer a one-click migration that copies
  `copilot_chat` route selection into `copilot_opus_4_7`.
- Do not delete `copilot_chat` automatically.

If user-created Copilot roles exist, keep them as stored roles but exclude them
from the main Copilot panel until multi-slot custom Copilot roles are designed.

## Testing Plan

Unit tests:

- Fixed Copilot roles are seeded when absent.
- Fixed Copilot roles are not deletable through the role delete endpoint.
- `copilot_deepseek_v4` defaults to one Pro route and has fallback disabled.
- Materialization runs before Copilot route resolution.
- `route_override` must belong to the selected role fallback chain.
- Claude Agent SDK adapter builds Anthropic official env correctly.
- Claude Agent SDK adapter builds DeepSeek official env correctly.
- Unsupported routes return a structured compatibility error.
- Runtime thinking and effort settings map to `ClaudeAgentOptions`.
- `tools` and `allowed_tools` are both set explicitly.

Integration tests with fake SDK:

- WebSocket request with `role_name=copilot_opus_4_7` uses the Opus role.
- WebSocket request with `role_name=copilot_deepseek_v4` uses the DeepSeek role.
- Fake SDK receives expected `ClaudeAgentOptions`.
- First route failure falls back only when role fallback is enabled.
- DeepSeek V4 Pro failure does not fallback to Flash.
- Compatibility test returns phase-level results.

Live smoke tests:

- Manual only.
- Run text smoke for Anthropic official Opus route.
- Run text smoke for DeepSeek V4 Pro route.
- Run read-tool smoke for both roles.
- Run edit-tool smoke before enabling edit tools by default for DeepSeek.

Frontend tests:

- Copilot role cards show SDK badges.
- SDK selector changes visible compatibility requirements.
- DeepSeek card shows fallback disabled.
- Agent compatibility test CTA warns about provider cost.
- Copilot panel sends `role_name`.
- Model picker only shows selected role routes.

## Acceptance Criteria

- Studio displays exactly two fixed Copilot role cards by default.
- Each Copilot role shows a runtime badge, initially `Claude Agent SDK`.
- `copilot_deepseek_v4` defaults to DeepSeek V4 Pro and does not fallback.
- Claude Agent SDK compatibility test validates runtime-specific requirements,
  not only raw model generation.
- DeepSeek official route uses `/anthropic` base URL and `ANTHROPIC_AUTH_TOKEN`
  when executed through Claude Agent SDK.
- Unsupported provider routes produce a clear compatibility error.
- Normal graph-agent roles continue to work unchanged.
- No secrets are printed in logs or test responses.

## Implementation Order

1. Add role schema fields and fixed role seeding.
2. Add Copilot role materialization and route override validation.
3. Add `ClaudeAgentSdkAdapter`.
4. Add route-level and role-level agent compatibility test endpoints.
5. Update Copilot WebSocket payload to include `role_name`.
6. Split Copilot role UI from graph-agent role UI and add SDK badges.
7. Add frontend and backend tests.
8. Run manual live smoke tests for Opus 4.7 and DeepSeek V4 Pro.

## Open Decision Already Resolved

DeepSeek V4 default is Pro, not Flash. The fixed DeepSeek Copilot role must not
fallback to Flash unless the user explicitly changes the role design in a future
iteration.
