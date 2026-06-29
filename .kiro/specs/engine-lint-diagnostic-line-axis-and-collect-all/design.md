# Design — Engine lint: file-absolute diagnostic lines + collect-all

> Process note: this spec was written **after** most of the work shipped (it was
> first dispatched via ad-hoc `docs/handoffs/*.md` instead of a kiro spec — the miss
> that caused two agents to edit `loader.py` concurrently). It retro-documents the
> design and, crucially, captures the **one remaining task** + the **independent
> re-audit** so all work converges on `tasks.md` (single source of truth).
> Prior handoffs folded in here:
> `docs/handoffs/engine-lint-collect-all-diagnostics.md`,
> `docs/handoffs/audit-request-engine-line-axis-followup.md`.

## D1 — Line coordinate system (the core insight)
Frontmatter errors are FILE-absolute (`_frontmatter_key_line` counts `splitlines()`
over the whole file). Body errors via `_xml_line` are BODY-relative (parser
`_strip_frontmatter` renumbers the body from 1). The editor marks the **full file**,
so body diagnostics MUST be file-absolute.

**Mechanism:** `loader.py::_body_file_line(path, body, offset)` — `body` is a suffix
of the file content, so `content.rfind(body)` anchors the body start exactly; map
the offset to a file line. (`parser.py::_body_offset_to_file_line` mirrors it for the
parser-side `scan_forbidden_topology_tags`; parser can't import loader = circular.)

## D2 — GRAPH.md `<phase>` diagnostics: separate diag field (NOT flip line_start)
`PhaseTokenInfo.line_start` is **serialized in `cache.py` (122/204)** and feeds
hash-locked round28 / source-map fixtures. Flipping it to file-absolute risks a
hash shift that can't be cleanly re-baselined on Windows. Instead add
`BodyPhaseRef.diag_line: int` (file-absolute, computed at construction) — `BodyPhaseRef`
is **not serialized** (verified: `cache.py` references `PhaseTokenInfo`, never
`BodyPhaseRef`) — and point the `<phase>` diagnostics at `ref.diag_line`.

## D3 — Collect-all seam
Accumulate per-node defects, raise once at a barrier before the post-loop validators.
The first defect stays the primary `payload`; the full set rides
`exc.compile_result.issues` (`CompileResult(issues=[CompileIssue(...)])`), which
`skills.py::_compile_errors_from_exception` already maps to `CompileError[]`. Location
uses the skill-RELATIVE path so Studio's `file:line` split isn't tripped by a Windows
`C:` drive colon. Structural errors (pre-loop) keep fail-fast.

## D4 — Current status (verified)
DONE: P1 role/goal/action lines · P2 collect-all · P5 empty-action · sibling
migration (agent unknown-tag/step/protocol/example/mention) · GRAPH
phase-id-invalid · phase-cycle (self-dep) · depends-unknown · **phase-island**
(fixed concurrently) · parser `scan_forbidden_topology_tags` · round14 Windows
fixture (`re.sub` repl → lambda). Verified locally: line-location tests, round14
21/21, full suite 14-failed/1369-passed/0-errors (14 = pre-existing Windows/env
noise), mypy --strict + ruff clean.

OPEN (see tasks.md):
- **Multi-node cycle** `[F-v3-graph-phase-cycle] cycle detected: a -> b -> c`
  (`loader.py:1388-1392`, inside `_validate_acyclic_graph`'s `visit`) still passes
  **hardcoded `1`**. It must use the offending cycle node's `diag_line`. Needs a
  `{name: diag_line}` map threaded into `_validate_acyclic_graph` (build it in
  `_validate_graph_topology` from `body_phase_refs`, pass it down; reuse for the
  island map too). Add a regression test (a→b→a cycle → file line, not 1).
- **Independent re-audit** of the whole change (implementer ≠ auditor).

## D5 — Concurrency / ownership (the reason this spec exists)
`loader.py` was being edited by two agents at once (one fixed island while the other
was about to). Going forward: ONE owner per task in `tasks.md`; no concurrent edits
to the same file. The remaining multi-node-cycle task is claimed by exactly one
implementer; a different agent does the re-audit.
