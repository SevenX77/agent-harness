---
status: Draft
created: 2026-05-27
owner: Engine + Studio
related_requirements: .kiro/specs/studio-gateway-runtime-schema-boundary/requirements.md
---

# Gateway Runtime Schema Boundary Research

## Finding

Gateway currently includes `display_name` in runtime-oriented schema and helper models:

- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py`
  - `ProviderEndpoint.display_name`
  - `ProviderRoute.display_name`
  - `ModelProfile.display_name`
  - import draft candidate display fields
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py`
  - `CanonicalModel.display_name`

The implementation of canonical display is:

```python
def _display_name(canonical_id: str) -> str:
    return canonical_id.replace(".", " ").replace("-", " ").title()
```

This is not a valid Studio display-name algorithm. It turns:

- `claude-opus-4.7` into `Claude Opus 4 7`
- `deepseek-v3.1-terminus-thinking` into `Deepseek V3 1 Terminus Thinking`
- `openai.gpt-5.5` into `Openai Gpt 5 5`

## How It Leaked Into Studio

The current Studio backend path is:

```text
provider model id
  -> Studio _route_slug()
  -> gateway canonicalize_model()
  -> ProviderRoute.display_name
  -> /api/llm/registry model_groups[].display_name
  -> frontend Available Models title
```

This makes a Gateway helper indirectly responsible for Studio UI text.

## Why Previous Audits Missed It

The previous audit rounds focused on large architecture risks:

- gateway should not understand Model Groups
- Studio Backend should materialize `fallback_chain`
- route/provider state lifecycle
- runtime health/circuit breaker
- provider kind and rate-limit bucket fields
- Role Test and Capability Test contracts
- Copilot fallback

Those audits checked whether the fields were consistently wired, but did not challenge whether each field belonged in its layer. Because `display_name` already existed in old gateway fixtures and tests, it looked like harmless metadata rather than a boundary violation. The reviews caught "Gateway must not understand Studio Model Groups" but not the smaller version of the same problem: "Gateway runtime schema must not carry Studio UI labels."

The missing audit checklist was field ownership:

| Field | Runtime needed? | Studio authoring? | Studio UI projection? | Import/admin only? |
|---|---:|---:|---:|---:|
| `provider_model_id` | yes | yes | debug only | yes |
| `route_id` | yes | yes | debug only | yes |
| `canonical_id` | grouping/materialization | yes | hidden/debug | yes |
| `display_name` | no | maybe | yes | yes |

Once viewed through this ownership lens, Gateway `display_name` is clearly misplaced.

## Boundary Decision

Gateway runtime schema should contain only fields used for:

- concrete route selection
- endpoint lookup
- provider request construction
- admission/lint
- runtime settings
- runtime health/fallback

Studio Backend owns:

- model group display name
- model family/section label
- provider label
- provider UI state
- role fit label
- warning copy
- user-facing test reports

## Non-Goals

1. Do not patch Gateway `_display_name()` to be smarter.
2. Do not keep compatibility fallback for runtime `display_name`.
3. Do not ask frontend to compute authoritative model names.
4. Do not move Studio Model Groups into Gateway.

