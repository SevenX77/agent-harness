# deerflow handover

Spec: `v1-reset-mvp-0-baseline-cleanup`
Date: 2026-04-28
Scope: T8 research only. Do not delete vendored files in this task.

## 1. PyPI status

Conclusion: **No public PyPI release found for `deerflow`**.

Commands run:

```bash
curl -s https://pypi.org/pypi/deerflow/json 2>&1 | head -30
```

Output:

```text
{"message": "Not Found"}
```

Cross-check:

```bash
pip index versions deerflow 2>&1 | head -5
```

Output:

```text
WARNING: pip index is currently an experimental command. It may be removed/changed in a future release without prior warning.
ERROR: No matching distribution found for deerflow
```

Decision branch: **B - no public release**. Do not add `deerflow>=...` to `pyproject.toml`; use inline/minimal replacement planning.

## 2. graph_agent -> deerflow imports

Task command:

```bash
grep -rn "from .* import .*deerflow\|import .*deerflow\|from .deerflow\|graph_agent\.deerflow" src/core/graph_agent --include="*.py" | grep -v "src/core/graph_agent/deerflow/" | head -50
```

Output:

```text
src/core/graph_agent/core/phase_executor.py:435:                from deerflow.tools.builtins import task_tool as deerflow_task_tool
```

The task command misses several absolute `from deerflow...` imports and relative `from ..deerflow...` imports, so I also ran:

```bash
rg -n "from (\.\.)?deerflow|from deerflow|import deerflow|graph_agent\.deerflow" src/core/graph_agent -g '*.py' -g '!src/core/graph_agent/deerflow/**'
```

Actual runtime import list:

| File:line | DeerFlow symbol | Purpose |
|---|---|---|
| `src/core/graph_agent/cognitive/middlewares.py:782` | `LoopDetectionMiddleware` from `deerflow.agents.middlewares.loop_detection_middleware` | Adds repeated tool-call loop protection to custom middleware chain. |
| `src/core/graph_agent/cognitive/middlewares.py:826` | `ClarificationMiddleware` from `deerflow.agents.middlewares.clarification_middleware` | Intercepts `ask_clarification` tool calls and returns LangGraph `Command(goto=END)`. |
| `src/core/graph_agent/models/resolver.py:415` | `get_app_config` from `deerflow.config` | Reads first DeerFlow model name as fallback default. |
| `src/core/graph_agent/models/resolver.py:434` | `create_chat_model` from `deerflow.models.factory` | Fallback to DeerFlow native model construction with `_bypass_hook=True`. |
| `src/core/graph_agent/core/phase_executor.py:388` | `ask_clarification_tool` from `deerflow.tools.builtins.clarification_tool` | Mounts clarification tool into phase tool list. |
| `src/core/graph_agent/core/phase_executor.py:435` | `task_tool` from `deerflow.tools.builtins` | Mounts subagent delegation tool when `phase.subagent_enabled`. |
| `src/core/graph_agent/core/runner.py:351` | `set_model_resolver_hook` from `deerflow.models.factory` | Registers graph_agent's `ModelResolver.resolve` into DeerFlow factory. |
| `src/core/graph_agent/core/harness.py:100` | `_resolve_sqlite_conn_str` from `deerflow.agents.checkpointer.provider` | Reuses DeerFlow SQLite path resolution for `STUDIO_CHECKPOINTER=sqlite:...`. |
| `src/core/graph_agent/core/harness.py:431` | `get_checkpointer` from `deerflow.agents.checkpointer.provider` | Auto checkpointer creation fallback. |

Import count: **9 actual graph_agent -> deerflow imports** outside the vendored directory. The compatibility shim in `src/core/graph_agent/__init__.py:13-18` also inserts `src/core/graph_agent` into `sys.path` so absolute `deerflow.*` imports resolve.

## 3. Recommended path

Recommended direction: **inline or re-home a minimal closure; do not depend on PyPI**.

Reasoning:

- `deerflow` has no public PyPI package discoverable through PyPI JSON or `pip index`.
- The graph_agent boundary only imports a small number of DeerFlow primitives, but `task_tool` pulls in a much larger subagent/lead-agent closure.
- MVP-0 is cleanup-oriented. The safest next step is to replace direct DeerFlow dependencies with graph_agent-owned modules, then remove the vendored package in T9 after smoke tests.

Pragmatic split:

1. Inline simple primitives directly:
   - `ask_clarification_tool`
   - `ClarificationMiddleware`
   - `LoopDetectionMiddleware`
   - `_resolve_sqlite_conn_str` or an equivalent graph_agent path resolver
   - `get_checkpointer` only if auto-checkpointer behavior remains needed
2. Move model hook behavior into graph_agent:
   - `set_model_resolver_hook`
   - `create_chat_model` fallback path
   - `get_app_config` fallback default lookup
3. Treat `task_tool` as conditional:
   - If B1 removes `parallel_delegate` / subagent support, delete this import path instead of inlining its closure.
   - If subagent support remains, inline the full subagent closure listed below.

## 4. Minimal inline closure if keeping current behavior

### Direct closure

These are required by the 9 actual graph_agent imports:

- `deerflow.tools.builtins.clarification_tool.ask_clarification_tool`
- `deerflow.agents.middlewares.clarification_middleware.ClarificationMiddleware`
- `deerflow.agents.middlewares.clarification_middleware.ClarificationMiddlewareState`
- `deerflow.agents.middlewares.loop_detection_middleware.LoopDetectionMiddleware`
- `deerflow.models.factory.create_chat_model`
- `deerflow.models.factory.set_model_resolver_hook`
- `deerflow.config.app_config.get_app_config`
- `deerflow.agents.checkpointer.provider._resolve_sqlite_conn_str`
- `deerflow.agents.checkpointer.provider.get_checkpointer`
- `deerflow.tools.builtins.task_tool.task_tool`

### Closure for `ask_clarification_tool`

Internal DeerFlow dependencies: none.

External dependencies:

- `langchain.tools.tool`

### Closure for `ClarificationMiddleware`

Internal DeerFlow dependencies: none.

External dependencies:

- `langchain.agents.AgentState`
- `langchain.agents.middleware.AgentMiddleware`
- `langchain_core.messages.ToolMessage`
- `langgraph.graph.END`
- `langgraph.prebuilt.tool_node.ToolCallRequest`
- `langgraph.types.Command`

### Closure for `LoopDetectionMiddleware`

Internal DeerFlow dependencies: none.

External dependencies:

- `langchain.agents.AgentState`
- `langchain.agents.middleware.AgentMiddleware`
- `langchain_core.messages.SystemMessage`
- `langgraph.runtime.Runtime`

### Closure for checkpointer support

Required DeerFlow files/symbols:

- `deerflow.agents.checkpointer.provider._resolve_sqlite_conn_str`
- `deerflow.agents.checkpointer.provider.get_checkpointer`
- `deerflow.agents.checkpointer.provider._sync_checkpointer_cm`
- `deerflow.config.app_config.get_app_config`
- `deerflow.config.app_config._app_config`
- `deerflow.config.checkpointer_config.CheckpointerConfig`
- `deerflow.config.checkpointer_config.get_checkpointer_config`
- `deerflow.config.paths.resolve_path`

External dependencies:

- `langgraph.checkpoint.memory.InMemorySaver`
- optional `langgraph.checkpoint.sqlite.SqliteSaver`
- optional `langgraph.checkpoint.postgres.PostgresSaver`
- `pydantic`
- `PyYAML`
- `python-dotenv`

### Closure for model factory support

Required DeerFlow files/symbols:

- `deerflow.models.factory.create_chat_model`
- `deerflow.models.factory.set_model_resolver_hook`
- `deerflow.models.factory._attach_profile_from_deerflow_config`
- `deerflow.config.get_app_config`
- `deerflow.config.app_config.AppConfig`
- `deerflow.config.model_config.ModelConfig`
- `deerflow.reflection.resolve_class`
- `deerflow.reflection.resolve_variable`
- `deerflow.models.openai_codex_provider.CodexChatModel`
- `deerflow.models.credential_loader.CodexCliCredential`
- `deerflow.models.credential_loader.load_codex_cli_credential`

Config closure loaded by `AppConfig.from_file()`:

- `deerflow.config.checkpointer_config`
- `deerflow.config.extensions_config`
- `deerflow.config.guardrails_config`
- `deerflow.config.memory_config`
- `deerflow.config.sandbox_config`
- `deerflow.config.skills_config`
- `deerflow.config.subagents_config`
- `deerflow.config.summarization_config`
- `deerflow.config.title_config`
- `deerflow.config.tool_config`
- `deerflow.config.tool_search_config`

External dependencies:

- `langchain_core.language_models.chat_models.BaseChatModel`
- provider packages named by config, resolved dynamically through `use: package.module:Class`
- `httpx` only if the Codex provider remains supported
- `pydantic`, `PyYAML`, `python-dotenv`

### Closure for `task_tool` if subagents remain

Required DeerFlow files/symbols:

- `deerflow.tools.builtins.task_tool.task_tool`
- `deerflow.agents.lead_agent.prompt.get_skills_prompt_section`
- `deerflow.agents.thread_state.ThreadState`
- `deerflow.agents.thread_state.SandboxState`
- `deerflow.agents.thread_state.ThreadDataState`
- `deerflow.subagents.SubagentExecutor`
- `deerflow.subagents.get_subagent_config`
- `deerflow.subagents.config.SubagentConfig`
- `deerflow.subagents.registry.get_subagent_config`
- `deerflow.subagents.builtins.BUILTIN_SUBAGENTS`
- `deerflow.subagents.builtins.general_purpose.GENERAL_PURPOSE_CONFIG`
- `deerflow.subagents.builtins.bash_agent.BASH_AGENT_CONFIG`
- `deerflow.subagents.executor.SubagentStatus`
- `deerflow.subagents.executor.SubagentResult`
- `deerflow.subagents.executor.cleanup_background_task`
- `deerflow.subagents.executor.get_background_task_result`
- `deerflow.subagents.executor.SubagentExecutor`
- `deerflow.tools.get_available_tools`
- `deerflow.tools.builtins.ask_clarification_tool`
- `deerflow.tools.builtins.present_file_tool`
- `deerflow.tools.builtins.view_image_tool`
- `deerflow.tools.builtins.tool_search.reset_deferred_registry`
- `deerflow.config.subagents_config.get_subagents_app_config`
- `deerflow.skills.load_skills`
- `deerflow.skills.loader`
- `deerflow.skills.parser`
- `deerflow.skills.types`
- `deerflow.skills.validation`

Additional closure currently pulled by `SubagentExecutor._create_agent(inherit_middlewares=True)`:

- `deerflow.agents.lead_agent.agent._build_middlewares`
- `deerflow.agents.middlewares.tool_error_handling_middleware.build_lead_runtime_middlewares`
- `deerflow.agents.middlewares.tool_error_handling_middleware.build_subagent_runtime_middlewares`
- `deerflow.agents.middlewares.memory_middleware.MemoryMiddleware`
- `deerflow.agents.middlewares.subagent_limit_middleware.SubagentLimitMiddleware`
- `deerflow.agents.middlewares.title_middleware.TitleMiddleware`
- `deerflow.agents.middlewares.todo_middleware.TodoMiddleware`
- `deerflow.agents.middlewares.view_image_middleware.ViewImageMiddleware`
- `deerflow.agents.middlewares.clarification_middleware.ClarificationMiddleware`
- `deerflow.agents.middlewares.loop_detection_middleware.LoopDetectionMiddleware`
- `deerflow.config.agents_config.load_agent_config`
- `deerflow.config.agents_config.load_agent_soul`
- `deerflow.config.summarization_config.get_summarization_config`
- `deerflow.models.create_chat_model`

This is the largest closure. If MVP-0 removes subagent support, do not inline this group.

## 5. Vendored DeerFlow internal dead-code check

Command:

```bash
grep -rn "lead_agent\|multimodal_config\|model_factory" src/core/graph_agent/deerflow --include="*.py"
```

Output:

```text
src/core/graph_agent/deerflow/subagents/executor.py:188:            from deerflow.agents.lead_agent.agent import _build_middlewares
src/core/graph_agent/deerflow/client.py:37:from deerflow.agents.lead_agent.agent import _build_middlewares
src/core/graph_agent/deerflow/client.py:38:from deerflow.agents.lead_agent.prompt import apply_prompt_template
src/core/graph_agent/deerflow/tools/builtins/task_tool.py:13:from deerflow.agents.lead_agent.prompt import get_skills_prompt_section
src/core/graph_agent/deerflow/agents/__init__.py:2:from .lead_agent import make_lead_agent
src/core/graph_agent/deerflow/agents/__init__.py:5:__all__ = ["make_lead_agent", "SandboxState", "ThreadState", "get_checkpointer", "reset_checkpointer", "make_checkpointer"]
src/core/graph_agent/deerflow/agents/lead_agent/__init__.py:1:from .agent import make_lead_agent
src/core/graph_agent/deerflow/agents/lead_agent/__init__.py:3:__all__ = ["make_lead_agent"]
src/core/graph_agent/deerflow/agents/lead_agent/agent.py:8:from deerflow.agents.lead_agent.prompt import apply_prompt_template
src/core/graph_agent/deerflow/agents/lead_agent/agent.py:277:    # Use the resolved runtime model_name from make_lead_agent to avoid stale config values.
src/core/graph_agent/deerflow/agents/lead_agent/agent.py:312:def make_lead_agent(config: RunnableConfig, *, inherit_middlewares: bool = True):
```

Findings:

- `multimodal_config`: no hits. If the file exists elsewhere, it is not referenced by vendored DeerFlow Python code under `src/core/graph_agent/deerflow`.
- `model_factory`: no hits. The active model factory module is `deerflow.models.factory`, not a `model_factory` module.
- `lead_agent`: not fully dead while `task_tool` / subagent execution remains. `task_tool` uses `lead_agent.prompt.get_skills_prompt_section`, and `SubagentExecutor._create_agent()` imports `lead_agent.agent._build_middlewares` when `inherit_middlewares=True`.
- `deerflow/client.py` references lead-agent internals but is not imported by graph_agent in the current non-vendored scan. It is a likely removal candidate after confirming no runtime entrypoint imports it.

## 6. T9 notes

- Before deleting vendored DeerFlow, replace or remove all 9 actual graph_agent -> deerflow imports listed above.
- Remove the `sys.path` hack in `src/core/graph_agent/__init__.py` after absolute `deerflow.*` imports are gone.
- If B1 removes subagents, delete the `phase.subagent_enabled` / `task_tool` path first; that avoids inlining the largest closure.
- After T9 edits, run an import smoke test and `pytest tests/graph_agent/ -x --tb=short`.
