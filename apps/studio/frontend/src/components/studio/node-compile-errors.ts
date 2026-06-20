import type { CompileError, LintError } from "@/api/types"

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
 * Realtime-lint counterpart of {@link compileErrorsByNode}: group flat `LintError[]`
 * (from the debounced `/lint` call) by the phase node they belong to, derived from
 * each diagnostic's `file` path (`phases/<id>/...`).
 *
 * Realtime lint marks context only — workflow 03_compile decision: "only mark red in
 * context, do not flood a global panel/toast mid-edit". This per-node bucketing is the
 * skeleton that future field-level Monaco markers (Wave 2) project onto; graph-level
 * diagnostics (GRAPH.md or no/undefined phase path) are not attributable to a node and
 * are omitted, exactly like the compile path.
 */
export function lintErrorsByNode(
  errors: readonly LintError[] | null | undefined,
): Record<string, LintError[]> {
  const byNode: Record<string, LintError[]> = {}
  for (const error of errors ?? []) {
    const file = error?.file
    if (typeof file !== "string") {
      continue
    }
    const match = PHASE_FILE_RE.exec(file)
    if (!match) {
      continue
    }
    const phaseId = match[1]
    const bucket = byNode[phaseId] ?? (byNode[phaseId] = [])
    bucket.push(error)
  }
  return byNode
}
