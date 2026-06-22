# Claude Code — Agent Harness

The canonical, cross-tool project rules live in **[AGENTS.md](AGENTS.md)** —
baseline & environment, CI gates, the three-module architecture, and the
standard documents. Read it first; it is imported below so it is always in
context.

> **Frontend UI task?** Before planning or touching anything under
> `apps/studio/frontend`, first read that folder's own
> [`apps/studio/frontend/CLAUDE.md`](apps/studio/frontend/CLAUDE.md) — a
> directory-scoped override that swaps the heavy multi-agent PM workflow for a
> lightweight single-agent loop. Claude Code only auto-loads that nested file
> *lazily* (the moment you first read a file in that subtree), so a session
> starting at the repo root won't have it yet — load it explicitly at task start.

@AGENTS.md
