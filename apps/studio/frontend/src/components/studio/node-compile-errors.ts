import type { CompileError, GraphTopologyItem, LintError } from "@/api/types"

/**
 * Per-node compile-error channel (authoring R10 / canvas REQ).
 *
 * Compile/lint produces a flat `CompileError[]` keyed by skill. A node's compile
 * health is a SEPARATE visual channel from its run status (a node can be red for
 * a compile error without ever having run). This pure helper groups the errors
 * by the phase node they belong to, derived from each error's `file` path
 * (`phases/<id>/...`). Graph-level errors (GRAPH.md, or no phase path) are not
 * attributable to a phase node and are omitted here (the global compile-error
 * panel still surfaces them).
 *
 * N4 atom #35 (golden-field gate): the Studio shell's golden-vs-output-schema compile
 * error is a business-rule error with NO `file` — it carries `field = "<node_id>.<field>"`
 * instead (skills.py `_validate_golden_against_output_schema`). To paint the offending
 * agent node red we fall back to the `field` node-id prefix when `file` yields no phase.
 */

// Mirrors the backend's phase-path character class (skills.py `_relative_compile_path`
// emits `phases/<id>/...` where `<id>` matches `[A-Za-z0-9_-]+`). Keep these in sync so
// an upper-case or digit-leading phase id never silently loses its node badge.
const PHASE_FILE_RE = /(?:^|\/)phases\/([A-Za-z0-9_-]+)\//
// The golden-field gate's field is "<node_id>.<missing_field>"; the node id is the prefix
// before the first dot (node id char class matches the phase-path class above).
const FIELD_NODE_PREFIX_RE = /^([A-Za-z0-9_-]+)\./

/**
 * Resolve the phase node an error belongs to. Prefers the `file` phase path
 * (`phases/<id>/...`); for a file-less error (the golden-field gate) falls back to the
 * node-id prefix of `field` (`<node_id>.<field>`). Returns null when neither attributes
 * the error to a node (graph-level / unattributable).
 */
function compileErrorNodeId(error: CompileError | null | undefined): string | null {
  const file = error?.file
  if (typeof file === "string") {
    const fileMatch = PHASE_FILE_RE.exec(file)
    if (fileMatch) {
      return fileMatch[1]
    }
  }
  const field = error?.field
  if (typeof field === "string") {
    const fieldMatch = FIELD_NODE_PREFIX_RE.exec(field)
    if (fieldMatch) {
      return fieldMatch[1]
    }
  }
  return null
}

export function compileErrorsByNode(
  errors: readonly CompileError[] | null | undefined,
): Record<string, CompileError[]> {
  const byNode: Record<string, CompileError[]> = {}
  for (const error of errors ?? []) {
    const phaseId = compileErrorNodeId(error)
    if (phaseId === null) {
      continue
    }
    const bucket = byNode[phaseId] ?? (byNode[phaseId] = [])
    bucket.push(error)
  }
  return byNode
}

/**
 * Resolve the phase node a realtime/first-screen `LintError` belongs to. Mirrors the
 * manual-Compile {@link compileErrorNodeId} so both channels attribute identically:
 * prefer the engine's typed `phase_name`, then the `file` phase path (`phases/<id>/...`),
 * then the `field_path` node-id prefix (`<node_id>.<x>`). Returns null when none attributes
 * the error to a node (graph-level / unattributable).
 *
 * The `field_path` fallback is what surfaces GRAPH.md-located TOPOLOGY diagnostics
 * (e.g. `[F-v3-graph-phase-island]`, whose engine payload carries
 * `field_path="<phase>.depends_on"`) onto the node badge in realtime lint — previously
 * only the GRAPH.md editor markers + compile drawer showed them. Errors with no node
 * locator (no `phase_name`, a non-`phases/` file, no `<id>.` field) still degrade to the
 * file/drawer surface, so per-file phase diagnostics keep matching by `file` exactly as
 * before.
 */
function lintErrorNodeId(error: LintError | null | undefined): string | null {
  const phaseName = error?.phase_name
  if (typeof phaseName === "string" && phaseName) {
    return phaseName
  }
  const file = error?.file
  if (typeof file === "string") {
    const fileMatch = PHASE_FILE_RE.exec(file)
    if (fileMatch) {
      return fileMatch[1]
    }
  }
  const field = error?.field_path
  if (typeof field === "string") {
    const fieldMatch = FIELD_NODE_PREFIX_RE.exec(field)
    if (fieldMatch) {
      return fieldMatch[1]
    }
  }
  return null
}

/**
 * Realtime-lint counterpart of {@link compileErrorsByNode}: group flat `LintError[]`
 * (from the debounced `/lint` call) by the phase node they belong to via
 * {@link lintErrorNodeId} (phase_name → `phases/<id>/` file → `field_path` node-id prefix).
 *
 * Realtime lint marks context only — workflow 03_compile decision: "only mark red in
 * context, do not flood a global panel/toast mid-edit". This per-node bucketing is the
 * skeleton that field-level Monaco markers project onto; diagnostics with no resolvable
 * node locator are omitted (they degrade to the GRAPH.md editor markers + compile drawer).
 */
export function lintErrorsByNode(
  errors: readonly LintError[] | null | undefined,
): Record<string, LintError[]> {
  const byNode: Record<string, LintError[]> = {}
  for (const error of errors ?? []) {
    const phaseId = lintErrorNodeId(error)
    if (phaseId === null) {
      continue
    }
    const bucket = byNode[phaseId] ?? (byNode[phaseId] = [])
    bucket.push(error)
  }
  return byNode
}

/**
 * Adapt a realtime/first-screen `LintError` onto the `CompileError` shape the canvas node
 * tooltip renders (N3 atom #4). SkillNode's {@link import("@/components/nodes/SkillNode")
 * .formatNodeCompileError} reads `field`/`line`/`message`, so feeding lint into the node
 * channel only renames the engine's nearest-field locator (`field_path` → `field`) — NO
 * client-side field re-derivation, no second source of truth. Lint severity ('error'|
 * 'warning') maps to the CompileError axis ('fatal'|'warning'); a missing `field_path`
 * degrades to a node-level (field-less) badge entry, mirroring the manual-Compile path.
 */
export function lintErrorToCompileError(error: LintError): CompileError {
  return {
    file: error.file ?? null,
    line: error.line,
    field: error.field_path ?? null,
    severity: error.severity === "warning" ? "warning" : "fatal",
    message: error.message,
    error_code: error.error_code,
  }
}

interface ActiveLintSources {
  /** SkillDetail.lint_result.errors — the backend's first-screen lint of the on-disk skill. */
  firstScreenLint: readonly LintError[] | null | undefined
  /** SkillDetail.manifest_errors — first-screen manifest/graph-level diagnostics. */
  manifestErrors: readonly LintError[] | null | undefined
  /**
   * The realtime LintResult.errors lifted from the editor (null until the first debounced
   * lint resolves). An EMPTY array is a resolved-clean lint and overrides first screen.
   */
  realtime: readonly LintError[] | null | undefined
}

/**
 * Pick the active lint diagnostics for the canvas/properties projection (N3 atom #4).
 *
 * Three parallel sources, with realtime taking precedence (overlay semantics): the moment a
 * realtime lint has resolved (its errors array is non-null — even when empty/clean), it owns
 * the projection so the editor's live edits replace the stale first-screen snapshot. Before
 * any realtime lint, the first-screen SkillDetail sources (`lint_result` + `manifest_errors`)
 * seed the initial projection so a freshly-opened skill already shows its node badges.
 */
export function activeLintErrors({ firstScreenLint, manifestErrors, realtime }: ActiveLintSources): LintError[] {
  if (realtime != null) {
    return [...realtime]
  }
  return [...(firstScreenLint ?? []), ...(manifestErrors ?? [])]
}

/**
 * Merge the manual-Compile node channel ({@link compileErrorsByNode}) with the lint node
 * channel ({@link lintErrorsByNode}, pre-adapted via {@link lintErrorToCompileError}) per node,
 * keeping BOTH — neither source is dropped (N3 atom #4). The canvas today fed nodes from manual
 * Compile only; this lets first-screen + realtime lint co-exist with an outstanding Compile run.
 *
 * n2-canvas#10 (data-gap-viz): the data-gap channel ({@link dataGapErrorsByNode}) is also a
 * CompileError-by-node map, so the same merge folds it into the node's conflict-error channel —
 * a node then shows compile + lint + data-gap together. The merge is variadic-friendly: chain
 * `mergeNodeErrors(mergeNodeErrors(compile, lint), dataGap)`.
 */
export function mergeNodeErrors(
  compileByNode: Record<string, CompileError[]>,
  lintByNode: Record<string, CompileError[]>,
): Record<string, CompileError[]> {
  const merged: Record<string, CompileError[]> = {}
  for (const [nodeId, errors] of Object.entries(compileByNode)) {
    merged[nodeId] = [...errors]
  }
  for (const [nodeId, errors] of Object.entries(lintByNode)) {
    const bucket = merged[nodeId] ?? (merged[nodeId] = [])
    bucket.push(...errors)
  }
  return merged
}

/**
 * Project the backend per-phase field-supply (graph_topology[].field_supply) onto the
 * canvas node conflict-error channel (n2-canvas#10 data-gap-viz, PM 2026-06-20).
 *
 * The PM's pinned model: the CANVAS node's ONLY data-gap job is to display a compile-style
 * CONFLICT ERROR when a required input field is NOT supplied by the upstream blackboard — no
 * checkbox UI, no type-equality red-X. Field SELECTION stays in the i/o panel and is resolved
 * against the blackboard/state fields, not a specific upstream node's outputs.
 *
 * `compute_field_supply` (services/canvas_data_gap.py) already flags each input field
 * `supplied=false` (`source='none'`) when no upstream producer AND no graph-level input
 * supplies it. This collects those gaps and emits a CompileError per gap, keyed by the phase
 * id, in the SAME shape {@link compileErrorsByNode} / {@link lintErrorsByNode} produce, so it
 * merges into the existing node-error channel via {@link mergeNodeErrors} and renders through
 * the node badge/tooltip the canvas already has. A gap is not a source-location error, so it
 * carries no `file`/`line`; the offending input field is named on `field`.
 */
export function dataGapErrorsByNode(
  topology: readonly GraphTopologyItem[] | null | undefined,
): Record<string, CompileError[]> {
  const byNode: Record<string, CompileError[]> = {}
  for (const row of topology ?? []) {
    const gaps = (row.field_supply ?? []).filter((entry) => entry.supplied === false)
    if (gaps.length === 0) {
      continue
    }
    byNode[row.id] = gaps.map((entry) => ({
      file: null,
      line: null,
      field: entry.field,
      severity: "fatal",
      message: `Input field '${entry.field}' has no upstream supply (missing from blackboard)`,
    }))
  }
  return byNode
}
