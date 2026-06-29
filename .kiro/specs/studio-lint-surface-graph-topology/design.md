# Design — Surface engine topology diagnostics on the canvas (realtime-lint)

## D1 — The gap (located in code)

`Workspace.tsx:2005-2015` builds the node-error projection by merging two channels:
- manual Compile → `compileErrorsByNode` → `compileErrorNodeId`
  (`node-compile-errors.ts:34-50`): file `phases/<id>/` path **then a `field`
  node-id-prefix fallback** (`<node_id>.<x>`). So GRAPH.md-located compile errors
  with a node-id field DID badge the node.
- realtime + first-screen lint → `lintErrorsByNode` (`node-compile-errors.ts:78-96`):
  used the `phases/<id>/` file path **only**. A GRAPH.md-located topology diagnostic
  has `file="GRAPH.md"` → no match → dropped. **This asymmetry is the bug.**

GRAPH.md inline markers were never the gap: `lintErrorsForFile` keeps
`file==="GRAPH.md"` and `lintErrorsToMarkers` renders the line.

## D2 — The fix (frontend)

Add `lintErrorNodeId(error: LintError)` mirroring `compileErrorNodeId`, resolving:
`phase_name` → `phases/<id>/` file → `field_path` node-id prefix. Point
`lintErrorsByNode` at it. Backward compatible: per-file phase diagnostics still
match by `file`; only `<id>.`-shaped `field_path` (or `phase_name`) adds attribution,
so non-node graph-level errors (e.g. `field_path="io.inputs"`) map to a phantom
node id that no node renders — harmless, same as the manual channel.

The backend already forwards the engine locator: `_lint_error_from_exception`
(`skills.py:1652-1668`) copies `payload.field_path` → `LintError.field_path` and
`phase_id`/location → `phase_name`. So no backend change.

## D3 — The fix (engine, additive locator only)

`_validate_no_islands` emits the island diagnostic with
`field_path=f"{phase_id}.depends_on"`. The diagnostic **line** uses `ref.diag_line`
(the file-absolute field introduced by the line-axis spec) — NOT a new line concept
here. `_graph_fatal` already accepts `field_path`; `make_error_payload` carries it.
No code/contract change; round28 bijection untouched.

## D4 — Dependencies (in-tree, not yet on `main`)

This change rides on two in-flight, uncommitted pieces it does NOT own:
1. **`BodyPhaseRef.diag_line`** — from
   `engine-lint-diagnostic-line-axis-and-collect-all` (R1.3). My island line uses it.
2. **Frontend `lintErrorsForFile`** — an in-flight frontend lint-projection helper
   (`git show HEAD:field-compile-errors.ts` has no `lintErrorsForFile`). My GRAPH.md
   marker test imports it. Confirm its owner/landing before this lands.

## D5 — Coordination with the line-axis spec (one owner per file)

`loader.py::_validate_no_islands` is shared: the **line** (`diag_line`) is the
line-axis spec's; the **`field_path` locator** is this spec's. Both currently coexist
in the working tree. The line-axis spec's OPEN task 12 will re-thread the
`{name: diag_line}` map through `_validate_acyclic_graph` and "reuse for the island
map" — i.e. it re-edits this exact function. **That task MUST preserve the
`field_path=f"{phase_id}.depends_on"` argument on the island `_graph_fatal`.**

Recommended resolution (honors their D5 "one owner per file"): fold the island
`field_path` one-liner into the line-axis spec as a sub-item of its task 7/12 so
loader.py has a single editor; this spec then owns only the frontend and depends on
the engine emitting the locator. See `tasks.md` for the concrete split.
