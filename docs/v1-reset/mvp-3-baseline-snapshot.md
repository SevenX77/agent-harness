# MVP-3 Baseline Snapshot — Loader / Startup / Middleware

Date: 2026-04-29  
Scope: MVP-3 T0-prep audit only. Source/tests were read-only; this file is the only artifact written.

## 1. `loader.py` Size + SLOC Distribution

File: `src/core/graph_agent/core/loader.py`

Baseline:

- Physical lines: **776**
- Nonblank / noncomment SLOC: **654**
- Top-level non-function SLOC: **37**
- Top-level function count: **14**

SLOC was counted as nonblank, noncomment lines with function docstring lines excluded from per-function counts.

| Lines | Function | SLOC | Physical lines |
|---:|---|---:|---:|
| 49-60 | `_parse_output_example_or_raise` | 11 | 12 |
| 68-70 | `_skill_namespace` | 2 | 3 |
| 73-105 | `_load_skill_local_module` | 28 | 33 |
| 108-200 | `resolve_skill_resource` | 75 | 93 |
| 203-231 | `_resolve_reference_resource` | 24 | 29 |
| 234-239 | `_resolve_tool_reference` | 5 | 6 |
| 247-380 | `load_workflow_from_md` | 93 | 134 |
| 384-400 | `_append_steps_to_prompt` | 12 | 17 |
| 403-482 | `_render_skill_section_xml_tags` | 73 | 80 |
| 485-566 | `_render_output_format_markdown` | 58 | 82 |
| 569-603 | `_compose_agent_system_prompt` | 26 | 35 |
| 606-628 | `_inject_persona` | 15 | 23 |
| 632-668 | `_phase_from_agent_skill` | 31 | 37 |
| 671-776 | `_phase_from_graph_phase` | 92 | 106 |

Bucket distribution:

| SLOC bucket | Function count |
|---|---:|
| 1-10 | 2 |
| 11-25 | 4 |
| 26-50 | 3 |
| 51-100 | 5 |
| 101+ | 0 |

Largest functions:

1. `load_workflow_from_md`: 93 SLOC
2. `_phase_from_graph_phase`: 92 SLOC
3. `resolve_skill_resource`: 75 SLOC
4. `_render_skill_section_xml_tags`: 73 SLOC
5. `_render_output_format_markdown`: 58 SLOC

## 2. `runner.py` Startup Side-Effect Sites

File: `src/core/graph_agent/core/runner.py`

Audit command:

```bash
rg -n "os\\.environ|sys\\.path|sys\\.modules" src/core/graph_agent/core/runner.py
```

Result: **0 hits**.

Complete list:

| Pattern | Sites in `runner.py` |
|---|---:|
| `os.environ.*` | 0 |
| `sys.path.*` | 0 |
| `sys.modules.*` | 0 |

No 5-line context blocks exist because there are no matching sites in `runner.py`.

Related startup/env side effects outside `runner.py`, for MVP-3 T1/T10 planning:

| File:line | Site | Note |
|---|---|---|
| `core/harness.py:423` | `os.environ.get("STUDIO_CHECKPOINTER")` | Runtime checkpointer override |
| `core/harness.py:437` | `os.environ.get("GRAPH_AGENT_CHECKPOINTER_DB")` | SQLite checkpointer path |
| `models/factory.py:15` | `os.environ.get(name)` | API key lookup helper |
| `models/factory.py:38-39` | `GRAPH_AGENT_MODEL_PROVIDER`, `GRAPH_AGENT_MODEL`, `OPENAI_MODEL` | Model provider defaults |
| `models/resolver.py:411` | `GRAPH_AGENT_DEFAULT_ROLE` | Default LLM role |
| `core/personas.py:32` | `GRAPH_AGENT_PERSONA_PATH` | Persona registry search path |

## 3. Output Schema Path Resolver / `sys.modules`

Current status:

- Function named `_resolve_output_schema_path`: **not present** in current `loader.py`.
- MVP-2 baseline referred to `loader.py:485-567` as `_resolve_output_schema_path`; current code at the same range is `_render_output_format_markdown`.
- Current output schema dotted-path prompt rendering lives at `loader.py:485-566`.

Current implementation location:

| File:line | Function | Role |
|---|---|---|
| `core/loader.py:485-566` | `_render_output_format_markdown(output_schema_path, skill_base_dir=None)` | Splits dotted path, resolves module/class, renders prompt-side Markdown output format |
| `core/loader.py:509-517` | inside `_render_output_format_markdown` | `module_path, class_name = output_schema_path.rsplit(".", 1)` then `resolve_skill_resource(..., kind="schema")` or `importlib.import_module(...)` |
| `tools/md_to_json.py:34-66` | `_resolve_schema_from_path(path)` | Runtime schema resolver for `ctx["_md_schema_path"]`; reads `sys.modules` and falls back to importlib |
| `tools/md_to_json.py:543-546` | `md_to_json(...)` | Uses `_resolve_schema_from_path(path)` when only `_md_schema_path` is available |

`sys.modules` write/read sites related to schema/tool local modules:

```text
src/core/graph_agent/core/loader.py:90    if module_name in sys.modules:
src/core/graph_agent/core/loader.py:91        return sys.modules[module_name]
src/core/graph_agent/core/loader.py:99    sys.modules[module_name] = module
src/core/graph_agent/core/loader.py:103       sys.modules.pop(module_name, None)
src/core/graph_agent/core/loader.py:171   module = sys.modules.get(
```

Context:

```text
loader.py:73-105 _load_skill_local_module()
  - creates namespaced module name `_graph_agent_skill_.<hash>.<module_path>`
  - returns existing `sys.modules[module_name]` when loaded
  - writes `sys.modules[module_name] = module` before `exec_module`
  - pops that module on load failure

loader.py:108-200 resolve_skill_resource()
  - for `kind="schema"`, returns the resolved module
  - first checks `sys.modules.get("_graph_agent_skill_.<hash>.<module_path>")`
  - falls back to `_load_skill_local_module` or `importlib.import_module`
```

`md_to_json.py` has `sys.modules` read-only coupling:

```text
tools/md_to_json.py:46 module = sys.modules.get(module_str)
tools/md_to_json.py:49 for key, mod in list(sys.modules.items()):
tools/md_to_json.py:58 error text references sys.modules lookup failure
```

MVP-3 T5 risk: removing loader `sys.modules` writes requires a replacement module sandbox that also satisfies `md_to_json._resolve_schema_from_path` or eliminates that dependency.

## 4. Monkey-Patch / Patch-Like Scattered Sites

Source grep patterns included `setattr.*langchain`, `__patch__`, `pytest_plugins`, `_apply_.*patch`, `sys.modules`, and patch-related comments.

Production monkey-patch sites:

| File:line | Site | Effect |
|---|---|---|
| `models/reasoning_patch.py:23` | `_apply_reasoning_content_patch()` | One-time DeepSeek/ARK reasoning-content patch |
| `models/reasoning_patch.py:45-49` | `ChatCompletionMessage.model_config = {..., "extra": "allow"}` | Mutates OpenAI SDK Pydantic model config for extra fields |
| `models/reasoning_patch.py:56-70` | `_lcob._convert_dict_to_message = _patched_convert` | Mutates LangChain OpenAI inbound conversion to preserve `reasoning_content` |
| `models/reasoning_patch.py:76-90` | `_lcob._convert_message_to_dict = _patched_to_dict` | Mutates LangChain OpenAI outbound conversion to echo `reasoning_content` |
| `models/resolver.py:467` | `_apply_reasoning_content_patch()` | Patch application trigger when creating OpenAI-compatible providers |

Patch-like mutable module registry sites:

| File:line | Site | Effect |
|---|---|---|
| `core/loader.py:99` | `sys.modules[module_name] = module` | Registers skill-local module under namespaced key |
| `core/loader.py:103` | `sys.modules.pop(module_name, None)` | Removes partially loaded module on failure |

Explicit non-production/test-only patch sites:

| Pattern | Result |
|---|---|
| `pytest_plugins` | 0 hits |
| `setattr.*langchain` | 0 direct hits; LangChain mutation is assignment in `models/reasoning_patch.py`, not `setattr(...)` |
| test `monkeypatch.*` | Present across tests, intentionally excluded from production cleanup scope |

Patch-related comments that are not startup monkey patches:

| File:line | Note |
|---|---|
| `cognitive/finish.py:31` | Mentions applications can monkey-patch error templates; no code mutation |
| `skills/builtin/md-patch/script/patch_tools.py` | Domain tool named patch; not Python monkey patching |
| `tools/md_to_json.py` | Mentions md-patch workflow; not Python monkey patching |

## 5. Middleware Physical Inventory

Current middleware package/files:

| File | Middleware classes / factory |
|---|---|
| `src/core/graph_agent/cognitive/middlewares.py` | `WorkingMemoryMiddleware`, `DeadEndPruningMiddleware`, `AgentLoopIterationMiddleware`, `ValidationMiddleware`, `UnattendedClarificationMiddleware`, `create_custom_middlewares(...)` |
| `src/core/graph_agent/cognitive/clarification_middleware.py` | `ClarificationMiddlewareState`, `ClarificationMiddleware` |
| `src/core/graph_agent/cognitive/__init__.py` | re-exports `create_custom_middlewares` |

Derived classes:

| File:line | Class | Base | State schema |
|---|---|---|---|
| `cognitive/middlewares.py:86` | `WorkingMemoryMiddleware` | `AgentMiddleware[AgentState]` | default `AgentState` |
| `cognitive/middlewares.py:164` | `DeadEndPruningMiddleware` | `AgentMiddleware[AgentState]` | default `AgentState` |
| `cognitive/middlewares.py:249` | `AgentLoopIterationMiddleware` | `AgentMiddleware[AgentState]` | default `AgentState` |
| `cognitive/middlewares.py:292` | `ValidationMiddleware` | `AgentMiddleware[AgentState]` | default `AgentState` |
| `cognitive/middlewares.py:634` | `UnattendedClarificationMiddleware` | `AgentMiddleware[AgentState]` | default `AgentState` |
| `cognitive/clarification_middleware.py:25` | `ClarificationMiddlewareState` | `AgentState` | N/A |
| `cognitive/clarification_middleware.py:29` | `ClarificationMiddleware` | `AgentMiddleware[ClarificationMiddlewareState]` | `ClarificationMiddlewareState` via `state_schema` |

Decorated middleware methods:

| File:line | Method | Decorator | Hook |
|---|---|---|---|
| `cognitive/middlewares.py:139` | `WorkingMemoryMiddleware.before_model` | `@override` | before model call |
| `cognitive/middlewares.py:214` | `DeadEndPruningMiddleware.before_model` | `@override` | before model call |
| `cognitive/middlewares.py:270` | `AgentLoopIterationMiddleware.before_model` | `@override` | before model call |
| `cognitive/middlewares.py:608` | `ValidationMiddleware.wrap_tool_call` | `@override` | sync tool call interception |
| `cognitive/middlewares.py:621` | `ValidationMiddleware.awrap_tool_call` | `@override` | async tool call interception |
| `cognitive/middlewares.py:714` | `UnattendedClarificationMiddleware.wrap_tool_call` | `@override` | sync `ask_clarification` interception |
| `cognitive/middlewares.py:727` | `UnattendedClarificationMiddleware.awrap_tool_call` | `@override` | async `ask_clarification` interception |
| `cognitive/clarification_middleware.py:91` | `ClarificationMiddleware.wrap_tool_call` | `@override` | sync `ask_clarification` HITL interception |
| `cognitive/clarification_middleware.py:101` | `ClarificationMiddleware.awrap_tool_call` | `@override` | async `ask_clarification` HITL interception |

Factory / registration:

| File:line | Site | Registered middleware |
|---|---|---|
| `cognitive/middlewares.py:740-837` | `create_custom_middlewares(...)` | Creates ordered middleware list |
| `cognitive/middlewares.py:766-772` | factory branch | `AgentLoopIterationMiddleware` first when `agent_loop_iteration` and `phase_name` |
| `cognitive/middlewares.py:774-780` | factory branch | `WorkingMemoryMiddleware` |
| `cognitive/middlewares.py:782-789` | factory branch | `DeadEndPruningMiddleware` |
| `cognitive/middlewares.py:791-797` | factory branch | loop detection requested but currently disabled/log-only |
| `cognitive/middlewares.py:799-824` | factory branch | `UnattendedClarificationMiddleware` or `ClarificationMiddleware` |
| `cognitive/middlewares.py:825-835` | factory branch | summarization requested but currently disabled/log-only |
| `core/phase_executor.py:546-559` | phase execution | Calls `create_custom_middlewares(...)` |
| `core/phase_executor.py:560-569` | phase execution | Appends `ValidationMiddleware(...)` after factory middlewares |
| `core/phase_executor.py:586-590` | agent creation | Passes `middleware=phase_middlewares` to `create_agent(...)` |

Current effective middleware order in LLM phases:

1. `AgentLoopIterationMiddleware` when enabled and `phase_name` exists
2. `WorkingMemoryMiddleware`
3. `DeadEndPruningMiddleware`
4. `ClarificationMiddleware` or `UnattendedClarificationMiddleware`
5. `ValidationMiddleware` appended by `phase_executor`

Loop detection and summarization are requested by `phase_executor.py:553-557` but are no-op/log-only in `create_custom_middlewares` after MVP-0 cleanup.

## 6. Notes for MVP-3 Follow-Up

- `runner.py` has no direct env/path/module startup side effects; T10 should mostly validate that this stays true and may need to move remaining startup/env reads in harness/models/personas into `Settings` if the scope expands beyond `runner.py`.
- `_resolve_output_schema_path` no longer exists under that name. The functional coupling remains split between `loader._render_output_format_markdown`, `loader.resolve_skill_resource`, and `tools.md_to_json._resolve_schema_from_path`.
- The most invasive startup hack is `models/reasoning_patch.py`; it is already centralized in one module but applied lazily from `ModelResolver._create_openai_compatible`.
- Middleware is physically concentrated in two cognitive files, but registration is split: factory in `cognitive/middlewares.py`, final `ValidationMiddleware` append and `create_agent(..., middleware=...)` in `core/phase_executor.py`.
