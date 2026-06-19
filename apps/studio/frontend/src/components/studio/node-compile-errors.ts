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
 */

// Mirrors the backend's phase-path character class (skills.py `_relative_compile_path`
// emits `phases/<id>/...` where `<id>` matches `[A-Za-z0-9_-]+`). Keep these in sync so
// an upper-case or digit-leading phase id never silently loses its node badge.
const PHASE_FILE_RE = /(?:^|\/)phases\/([A-Za-z0-9_-]+)\//

export function compileErrorsByNode(
  errors: readonly CompileError[] | null | undefined,
): Record<string, CompileError[]> {
  const byNode: Record<string, CompileError[]> = {}
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
