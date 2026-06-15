import type { CompileError } from "@/api/types"

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

const PHASE_FILE_RE = /(?:^|\/)phases\/([a-z][a-z0-9_-]*)\//

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

/** Whether a node has at least one fatal compile error (vs. warnings only). */
export function hasFatalCompileError(errors: readonly CompileError[] | undefined): boolean {
  return (errors ?? []).some((error) => error.severity === "fatal")
}
