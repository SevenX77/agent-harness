# gateway MVP1 Alignment

## 定义

`gateway` is the model/provider/role routing platform block. It owns provider and route descriptors, capability matching, role resolution, fallback chains, runtime health/circuit state, and graph-agent model adapter behavior. HTTP glue is documented separately in `llm-copilot-http-api/`.

Source workflow basis: `01_workflows/00_settings-ux-spec.md:340`, `01_workflows/00_settings-ux-spec.md:361`, `01_workflows/00_settings-ux-spec.md:395`, `01_workflows/00_settings-ux-spec.md:433`.

## 接口契约

- Settings/API Keys produce provider endpoints, credentials, and model inventory.
- LLM Roles/Copilot produce abstract role mappings and fallback chains.
- Engine asks gateway/model resolver for executable chat model runtimes.
- Gateway tracks runtime health/circuits and projects statuses back to Settings.
- Companion platform doc: `llm-copilot-http-api/` owns `/api/llm` and `/api/copilot` HTTP/WS DTOs.

## F1. Provider And Model Registry

- 机制: represent providers, endpoints, models, capabilities, route status, and runtime policy.
- 决策: Settings UI edits concrete providers; gateway normalizes routable model facts.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:361` assigns API Keys provider responsibility.
- 测试: provider endpoint/model discovery produces stable registry response consumed by Settings.
- Status: live.
- 归属: platform `gateway`; region `settings`.

## F2. Canonical State Projection

- 机制: project provider/model/route state into canonical visible states and reasons.
- 决策: UI needs the six-state language from settings spec.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:255` records canonical state requirements.
- 测试: ready, untested, cooling_down, historical_ready, failed(reason), off/setup cases are distinguishable and old labels do not leak.
- Status: target-design.
- 归属: platform `gateway`; capability `studio-settings`.

## F3. Role Materialization And Resolution

- 机制: model groups and provider routes materialize into graph-agent and copilot role fallback chains; resolver returns executable routes.
- 决策: predict/run and copilot consume Settings-built bundles rather than own model config.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:395` defines LLM Roles; `01_workflows/00_settings-ux-spec.md:163` records materializer reuse.
- 测试: invalid active route blocks save; fallback order is stable; skipped routes produce warnings not silent loss.
- Status: live with state-label drift.
- 归属: platform `gateway`; capabilities `predict`, `run-execution`, `copilot-assist`.

## F4. Runtime Fallback And Health

- 机制: gateway chat model iterates fallback candidates, classifies failures, opens circuits, and emits fallback events.
- 决策: runtime reliability belongs below feature UI.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:462` records settings as cross-cutting dependency for runtime workflows.
- 测试: failing primary route falls back; cooling-down circuit affects projection; recovery clears route status.
- Status: live/partial.
- 归属: platform `gateway`; platform `state-engine`.

## F5. Copilot Role Boundary

- 机制: gateway resolves `copilot_chat` roles; actual Copilot SDK session/chat behavior belongs to copilot service/HTTP glue.
- 决策: gateway library should not know Copilot UI; it only resolves routes.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:433` assigns Copilot settings, while chat behavior is capability-owned.
- 测试: copilot role materializes separately from graph-agent roles; role test uses the same runtime path as chat.
- Status: partial; probe parity gap.
- 归属: platform `gateway`; docs `llm-copilot-http-api/`; capability `copilot-assist`.

## F6. Import Drafts And Runtime Descriptors

- 机制: import/provider draft evidence and runtime descriptors support Settings workflows without leaking raw backend internals.
- 决策: Settings should present reviewable provider/model changes before applying them.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:298` records draft/pipeline gaps.
- 测试: draft evidence survives refresh; apply produces registry/model group changes and websocket refresh.
- Status: partial live.
- 归属: platform `gateway`; region `settings`.

## 待 PM 补 gap

- Final distinction between "failed(reason)" and "historical_ready" copy in Settings.
