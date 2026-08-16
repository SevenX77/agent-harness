/**
 * The one authoritative reading of a diagnostic's file path.
 *
 * Every diagnostic path Studio receives — `LintError.file`, `CompileError.file` — is the
 * engine's `CompileIssue.source_path` rendered relative to the root of THIS compile
 * (`packages/graph-agent/src/graph_agent/core/compiler.py:19`; the rule and its rationale
 * are recorded in
 * `.kiro/specs/decision-2026-08-15-compile-diagnostics-name-the-file-they-are-in.md`).
 * A path is therefore an answer to "which file, counted from the compile root", and the
 * only way to read it is from the root outwards. Matching a fragment anywhere inside it
 * asks a different question and gets a different file's answer.
 *
 * Two consequences, both encoded here so the rule has exactly one definition:
 *
 *  - a root-graph phase owns `phases/<id>/...` starting at position 0. A phase inside a
 *    child skill arrives as `subgraph/<child>/phases/<id>/...` and belongs to no root
 *    node — the root phase hosting that child is named by its own `SUBGRAPH.md`, whose
 *    id is unrelated to the child directory name, so the path cannot name it;
 *  - comparing a diagnostic's path with the open file's path is an equality test between
 *    two root-relative strings, not a suffix test.
 */

/** Posix separators, no leading slash — so a path can be read from its first segment. */
export function normalizeDiagnosticPath(path: string): string {
  return path.replace(/\\/g, "/").replace(/^\/+/, "")
}

// Root-anchored on purpose (see module docstring). `<id>` mirrors the backend's phase-id
// char class (`skills.py` `_relative_compile_path` emits `phases/<id>/...`).
const ROOT_PHASE_FILE_RE = /^phases\/([A-Za-z0-9_-]+)\//

/**
 * The root-graph phase id that `path` names, or `null` when it names no root node
 * (graph-level files, workspace files, and every file inside a child skill).
 */
export function rootPhaseIdFromPath(path: string | null | undefined): string | null {
  if (typeof path !== "string" || !path) {
    return null
  }
  const match = ROOT_PHASE_FILE_RE.exec(normalizeDiagnosticPath(path))
  return match ? match[1] : null
}

/** True when `path` and `openFilePath` are the same file of the same compile root. */
export function isSameDiagnosticFile(path: string, openFilePath: string): boolean {
  return normalizeDiagnosticPath(path) === normalizeDiagnosticPath(openFilePath)
}

const ROOT_GRAPH_FILE = "GRAPH.md"

/**
 * True when a diagnostic located at `file` may still be placed on a root node by its
 * `field_path` alone.
 *
 * `field_path` is a locator INSIDE the file the diagnostic is in, so it only names a root
 * node when that file belongs to the root graph. Two cases legitimately need it:
 *
 *  - no file at all — the Studio golden-field gate emits `field = "<node_id>.<field>"`
 *    with `file: null` (`skills.py` `_validate_golden_against_output_schema`);
 *  - the root `GRAPH.md` — topology and io diagnostics live there and carry
 *    `<node>.depends_on` / `io.inputs.…` locators.
 *
 * A child skill's own graph arrives as `subgraph/<child>/GRAPH.md` and carries the child's
 * `io.outputs.required`; reading that as the ROOT graph's output block is the same
 * mis-attribution this module exists to prevent.
 */
export function fieldAxisCanNameARootNode(file: string | null | undefined): boolean {
  if (typeof file !== "string" || !file) {
    return true
  }
  return normalizeDiagnosticPath(file) === ROOT_GRAPH_FILE
}
