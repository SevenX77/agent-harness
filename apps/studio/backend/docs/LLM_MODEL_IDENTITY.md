# LLM Model Identity And Grouping

This backend area owns the rules that turn provider model IDs into Studio
Available Models groups.

## Source Modules

- `app/services/llm_model_identity.py`
  - Tokenizes a provider model ID after protecting known date/version shapes.
  - Infers owner/family/section, such as Anthropic/Claude or DeepSeek.
  - Produces route-level display identity with structured token fields.
- `app/services/llm_model_groups.py`
  - Converts the route-level identity into a user-facing model group identity.
  - Produces the model group key used by `/api/llm/registry`.
  - Classifies release/snapshot tokens, capability tokens, and provider route
    channel tokens so they do not become separate model cards.

Routers should not add provider/model-name special cases. If Available Models
grouping is wrong, update `llm_model_identity.py` or `llm_model_groups.py` and
add focused tests under `tests/services/test_llm_model_identity.py`.

## Model Group Rule

Available Models groups represent stable model identity, not every physical
provider route name.

The group display name keeps:

- model family and major version, such as `Claude Haiku 4.5` or `DeepSeek V4`
- stable product variants, such as `Flash`, `Pro`, `Exp`, or `Speciale`

The group display name excludes:

- release/snapshot tokens: `20251001`, `20250805`, `260425`, `2025-09-29`,
  terminal valid MMDD suffixes such as `0324`, and preview month/year suffixes
  such as `05 2026`
- capability tokens: `thinking`, `reasoning`, `vision`, `tools`, etc.
- provider route channel tokens: `free`, `or`

Tokenization intentionally treats provider punctuation as separators after
date/version protection. In other words, `4.7`, `4-7`, `4_7`, and `V3-1` are
first normalized as model versions, then remaining punctuation such as `/`,
`.`, `-`, `_`, `:`, or `~` only separates tokens. This lets route channels such
as `:free` collapse into the provider route option instead of creating a
separate model group.

Those excluded tokens remain meaningful:

- exact execution still uses the original `route_id`
- provider cards still show the provider route as a route option
- capability tokens can drive model capability badges such as `Thinking`
- release/channel tokens can remain in backend route IDs and diagnostics

## Registry Flow

`/api/llm/registry` builds Available Models through this flow:

1. Load `ProviderRoute` records from credentials.
2. Filter route availability for model groups.
3. Call `project_model_group_identity(route, endpoint)` for each route.
4. Group routes by `ModelGroupIdentityProjection.key`.
5. Render one model group card per key, with exact provider routes listed under
   `provider_models`.

This means `claude-haiku-4-5` and `claude-haiku-4-5-20251001` should produce
one `Claude Haiku 4.5` model group, while their exact provider route IDs remain
available for execution.
