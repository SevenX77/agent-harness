# DeerFlow Harness — Source Notice

This directory contains code from the [DeerFlow](https://github.com/bytedance/deer-flow) project,
developed by ByteDance and licensed under the **MIT License** (see `LICENSE` in this directory).

## Source Information

- **Repository**: https://github.com/bytedance/deer-flow
- **Package**: `deer-flow/backend/packages/harness/deerflow/`
- **Copy Date**: 2026-03-28
- **Commit**: Local copy from project `deer-flow/` directory

## Modifications

All modifications to the original DeerFlow code are marked with `# MODIFIED` comments.
The following files have been modified:

1. `models/factory.py` — `create_chat_model()` delegates to external Model Resolver via hook
2. `agents/lead_agent/agent.py` — `_build_middlewares()` supports custom middleware injection; also carries **Task 2.7** changes that let `_build_middlewares()` and `make_lead_agent()` accept `inherit_middlewares: bool = True`, so subagents can reuse the full lead middleware chain
3. `agents/middlewares/tool_error_handling_middleware.py` — `SandboxMiddleware` configurable
4. `subagents/executor.py` — **Task 2.7**: `SubagentExecutor` accepts `inherit_middlewares: bool = True` and, when True, builds middlewares via the lead agent's shared `_build_middlewares()` rather than the thin `build_subagent_runtime_middlewares`

## Upstream syncs applied

The vendored copy has received the following upstream bug fixes on top of the
2026-03-28 snapshot (re-applied semantically where structure diverged):

- `#2251` Memory update cache corruption + thread-safety (`agents/memory/updater.py`)
- `#2351` Clarification idempotency (`agents/middlewares/clarification_middleware.py`)
- `#2107` Skill parser YAML + tool dedup (`skills/parser.py`, `tools/tools.py`)
- `#2305` Subagent inherits parent `tool_groups` (`agents/lead_agent/agent.py`, `tools/builtins/task_tool.py`)

Upstream PRs explicitly not synced:

- `#2321` — frontend-only (vendored copy has no frontend)
- `#2332` — uploads opt-in harden; our `utils/file_conversion.py` is a 47-line
  stub without the `_get_pdf_converter` path the patch targets, and the HTTP
  gateway the security gate protects is not vendored

## Trimmed Modules

The following DeerFlow modules were removed (not needed for this project):

- `community/` — Third-party tool integrations (Tavily, Jina, Firecrawl, etc.)
- `mcp/` — MCP server support
