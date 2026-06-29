# Handoff — Engine loader: collect-all diagnostics + correct line attribution + consistent empty-tag detection

> Status: **handoff for an engine-scoped agent**. Authored 2026-06-29.
> Boundary: this is a `packages/graph-agent` (engine) change — KEEP-MAIN frozen core,
> so it is explicitly scoped to the engine and MUST land with engine TDD. The Studio
> auditor (me) reviews; they do not implement.

## Why (user intent, first-principles)

> "不管是 lint 还是 compile,这不是在跑 skill 的运行期,为什么要中断?逻辑很迷,
> 当然是把所有问题都找出来。"

Compile/lint are **static analysis**, not the run phase. They must report **every**
problem in one pass, not abort at the first. Today the loader is fail-fast: the first
`_fatal(...)` raises and aborts, so the user fixes one error, recompiles, hits the next.

Aligned design: real-time lint is "mark context only" while the **manual compile drawer
is the full error list** (`docs/studio/mvp1/02_capabilities/compile-lint/mvp1-alignment.md`
F1/F2). A full list is only possible if the engine collects all diagnostics.

## The three coupled problems (all in one file)

All live in `packages/graph-agent/src/graph_agent/core/loader.py`.

### P1 — wrong line attribution (errors pinned to line 1)
- `loader.py:1715` `_fatal(path, 1, "[F-v3-agent-role-missing] Agent body requires <role>")`
- `loader.py:1717` `_fatal(path, 1, "[F-v3-agent-goal-missing] Agent body requires <goal>")`
- `loader.py:1671` `_fatal(path, 1, "[F-v3-logic-actions-empty] LOGIC.md requires <action> tags")`

Line `1` is hardcoded → the marker lands on the frontmatter `---` (line 1), not the
offending tag. Studio cannot re-derive the line (lint is engine-owned single source of
truth; the frontend must not invent a second list), so this must be fixed in the engine.

Desired:
- When the tag EXISTS but is empty (`<role></role>`), point to the tag's line. The helper
  `_xml_line(body, body.lower().find("<role"))` already exists and is used a few lines
  above for the unknown-tag errors — reuse it.
- When the tag is entirely MISSING, point to the body start (first line after the
  frontmatter `---`), not line 1. (Confirm the intended target against
  `docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md` — the
  `error_registry.py` entry for `[F-v3-agent-role-missing]` links there.)

### P2 — fail-fast → collect-all (the big one)
- `_fatal` is `def _fatal(...) -> NoReturn:` (`loader.py:323`) — it `raise`s `SkillLoadError`.
- It is called **89 times** across `loader.py`. The whole loader assumes "first error aborts".

Desired: one compile/lint pass returns **all** independent diagnostics. Concretely the
user wants role-missing AND goal-missing reported together (today goal at `:1717` is never
reached because role at `:1715` already raised).

This is the LARGE part. It is NOT a search-replace: code after each `_fatal` frequently
assumes the validated state (e.g. parsed `role`/`goal`/`actions` are then used), so you
cannot simply "record and continue" everywhere. Strategy options to evaluate:
- Introduce a diagnostics accumulator (list) threaded through the parse/validate
  functions; convert independent checks (the per-node body checks like role/goal/action
  presence, unknown-tag scans, schema field checks) to append instead of raise; keep a
  single raise/return at well-defined barriers where continuing is unsafe.
- Group by "phase/file unit": collect all diagnostics for a node before moving on, so one
  broken node doesn't hide another node's errors.
- Preserve fail-fast for **structural** errors that make further parsing impossible
  (e.g. missing GRAPH.md, unparseable YAML) — those legitimately abort. Only the
  **content/whitelist** checks need to become collect-all.

Decide the seam deliberately and document it; do not flatten 89 raises blindly.

### P5 — agent vs logic empty-tag detection is inconsistent
- Agent (`loader.py:1706-1717`): `role = blocks.get("role"); if not role: _fatal(...)`.
  `not role` treats an empty `<role></role>` as missing. Same for goal.
- Logic (`loader.py:1663-1672`, `_extract_logic_actions`): `action = match.group(1).strip();
  if action: actions.append(action)` then `if not actions: _fatal(...)`. So a single empty
  `<action></action>` errors (zero non-empty), but an empty `<action>` **alongside a
  filled one is silently ignored** — logic never flags the empty tag itself.

Desired: one consistent rule. Recommended (matches the agent's stricter check + the user's
intent that required tags be non-empty): an empty `<action></action>` is itself a
diagnostic, even when other actions are filled. Confirm the exact wording/error code with
the skill-syntax design before changing.

## Tests (engine TDD — write/adjust FIRST)

- Spec lists the error codes: `packages/graph-agent/spec/features.yaml:246`
  (`[F-v3-agent-role-missing]`) and the round28 fixtures. Keep codes stable.
- Existing assertions to honor / update:
  - `tests/e2e/test_round14_compiler_e2e.py:360` maps `("agent-role-missing", _drop_agent_role, "[F-v3-agent-role-missing]")` — collect-all must still surface this code.
  - `tests/core/test_compiler_line_locations.py` — line attribution; ADD cases asserting role/goal/action errors land on the tag line (or body start when missing), NOT line 1.
- ADD: a multi-error fixture (agent body missing BOTH role and goal) asserting BOTH
  diagnostics come back from ONE compile — the core P2 regression lock.
- ADD: logic body with one filled + one empty `<action>` asserting the empty one is flagged (P5).
- Run the full engine suite green: `uv run pytest packages/graph-agent/tests` plus
  `uv run mypy --strict packages/graph-agent/src` and `uv run ruff check packages/graph-agent`.

## Auditor checklist (Studio side, me)

1. Diagnostics are collected, not fail-fast, for content/whitelist checks; structural
   aborts preserved and justified.
2. role+goal (and multi-node) errors appear together in one compile result.
3. Each diagnostic carries the correct line (tag line / body start), never hardcoded 1.
4. agent/logic empty-tag detection unified per the design.
5. Error codes unchanged; `features.yaml` + round14/round28 still green; new multi-error
   and line-location tests present and passing; mypy/ruff clean.
6. No Studio-side change needed — the Studio lint/compile projections already render
   whatever the engine returns (per-file markers, node badges, compile drawer).
