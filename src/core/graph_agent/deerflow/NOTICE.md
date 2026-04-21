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
2. `agents/lead_agent/agent.py` — `_build_middlewares()` supports custom middleware injection
3. `agents/middlewares/tool_error_handling_middleware.py` — `SandboxMiddleware` configurable

## Trimmed Modules

The following DeerFlow modules were removed (not needed for this project):

- `community/` — Third-party tool integrations (Tavily, Jina, Firecrawl, etc.)
- `mcp/` — MCP server support
