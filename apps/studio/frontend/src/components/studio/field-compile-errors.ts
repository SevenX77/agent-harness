import type { CompileError, LintError } from "@/api/types"

/**
 * Field-level near-projection of lint/compile diagnostics (authoring N3 atom #5/#6).
 *
 * The engine's ErrorPayload pins a typed nearest-field locator (`field_path`) plus an
 * optional `line`. The Studio shell now forwards both on `LintError` (models/errors.py →
 * api/types.ts). This pure module turns that flat list into the two field-grained
 * projections the design calls for, with NO second source of truth and NO client-side
 * field re-derivation — we read the engine's axis verbatim:
 *
 *  - {@link fieldErrorsByKey}: group a single node's errors by `field_path` so the
 *    Properties panel can mark the offending field. Errors with no `field_path` are
 *    omitted here — they degrade to the node-level badge (atom #4).
 *  - {@link lintErrorsToMarkers}: map line-bearing errors to Monaco marker descriptors for
 *    IDE-style inline markers (atom #6). Errors with no `line` are dropped — they degrade
 *    to the file-level diagnostics strip, never guessing a line.
 *
 * Both are the field/line counterparts of {@link import("./node-compile-errors")}, which
 * stays the node-level (file → `phases/<id>/`) channel.
 */

// Mirrors the node channel's phase-path char class (skills.py `_relative_compile_path`
// emits `phases/<id>/...`, `<id>` = `[A-Za-z0-9_-]+`). Used only as the fallback node
// scope when an error carries no `phase_name`.
const PHASE_FILE_RE = /(?:^|\/)phases\/([A-Za-z0-9_-]+)\//

function errorPhaseId(error: LintError): string | null {
  if (typeof error.phase_name === "string" && error.phase_name) {
    return error.phase_name
  }
  const file = error.file
  if (typeof file !== "string") {
    return null
  }
  const match = PHASE_FILE_RE.exec(file)
  return match ? match[1] : null
}

export function lintErrorsForPhase(
  errors: readonly LintError[] | null | undefined,
  phaseId: string,
): LintError[] {
  return (errors ?? []).filter((error) => {
    if (errorPhaseId(error) === phaseId) {
      return true
    }
    const field = error?.field_path
    return typeof field === "string" && field.startsWith(`${phaseId}.`)
  })
}

/**
 * Group the selected node's errors by the engine's `field_path` (nearest field).
 *
 * Only errors attributable to `phaseId` (by `phase_name`, else the `file` phase path) and
 * carrying a non-empty `field_path` are kept; everything else degrades to the node badge.
 */
export function fieldErrorsByKey(
  errors: readonly LintError[] | null | undefined,
  phaseId: string,
): Record<string, LintError[]> {
  const byField: Record<string, LintError[]> = {}
  for (const error of errors ?? []) {
    const field = error?.field_path
    if (typeof field !== "string" || !field) {
      continue
    }
    if (errorPhaseId(error) !== phaseId) {
      continue
    }
    const bucket = byField[field] ?? (byField[field] = [])
    bucket.push(error)
  }
  return byField
}

/**
 * Adapt manual-Compile `CompileError[]` onto the `LintError` field axis so the Properties
 * panel projects field markers from one DTO via {@link fieldErrorsByKey}.
 *
 * Both DTOs already carry the engine's field locator (CompileError.field ←→ LintError
 * .field_path); this just renames it — no client-side field re-derivation. CompileError
 * has no `phase_name`, so scoping falls back to its `file` phase path (handled by
 * {@link fieldErrorsByKey}). Until the realtime lint result is lifted to the workspace,
 * this is the field-bearing source available to the panel (design N3 atom #5).
 */
export function compileErrorsToFieldLintErrors(
  errors: readonly CompileError[] | null | undefined,
): LintError[] {
  return (errors ?? []).map((error) => ({
    file: error.file,
    line: error.line,
    column: null,
    error_code: "compile_error",
    severity: error.severity === "warning" ? "warning" : "error",
    message: error.message,
    phase_name: null,
    field_path: error.field,
    source_path: null,
  }))
}

/**
 * Project the whole-skill lint result down to the diagnostics of ONE open file.
 *
 * Realtime lint is engine-owned and intentionally whole-skill: the SAME `LintResult`
 * feeds the canvas node badges (by phase), the Properties panel (by field), AND the
 * editor (by line). Each surface is a pure projection of that one source — this is the
 * editor's "by file" slice, the sibling of {@link fieldErrorsByKey} (by phase) and
 * {@link lintErrorsToMarkers} (by line). Per compile-lint design F1 ("real-time lint marks
 * context only"), the editor shows only THIS file's diagnostics; cross-file / structural /
 * file-less errors degrade to the manual Compile drawer, never as inline marks here.
 *
 * Matching is separator-insensitive and tolerates an absolute sandbox-path leak (the
 * realtime lint normally strips the throwaway sandbox prefix to a skill-relative path, but
 * a leak would end with the relative path). Errors with no `file` are skill-level and dropped.
 */
export function lintErrorsForFile(
  errors: readonly LintError[] | null | undefined,
  filePath: string,
): LintError[] {
  const target = filePath.replace(/\\/g, "/").replace(/^\/+/, "")
  if (!target) {
    return []
  }
  return (errors ?? []).filter((error) => {
    if (typeof error?.file !== "string" || !error.file) {
      return false
    }
    const candidate = error.file.replace(/\\/g, "/").replace(/^\/+/, "")
    return candidate === target || candidate.endsWith(`/${target}`)
  })
}

/** Monaco-shaped marker descriptor (severity kept as a string so this module is monaco-free). */
export interface LintMarkerDescriptor {
  startLineNumber: number
  endLineNumber: number
  startColumn: number
  endColumn: number
  message: string
  severity: LintError["severity"]
  code: string
}

/**
 * Map line-bearing lint errors to Monaco marker descriptors (atom #6).
 *
 * No `line` → dropped (degrade to the file-level strip). No `column` → mark the whole line
 * from column 1. `endColumn` is left generous so a column-less marker spans the line.
 */
export function lintErrorsToMarkers(
  errors: readonly LintError[] | null | undefined,
): LintMarkerDescriptor[] {
  const markers: LintMarkerDescriptor[] = []
  for (const error of errors ?? []) {
    const line = error?.line
    if (typeof line !== "number" || !Number.isFinite(line) || line < 1) {
      continue
    }
    const startColumn = typeof error.column === "number" && error.column >= 1 ? error.column : 1
    markers.push({
      startLineNumber: line,
      endLineNumber: line,
      startColumn,
      // No precise end column from the engine; span to a large column so the whole token/line
      // is underlined. Monaco clamps this to the actual line length.
      endColumn: startColumn === 1 ? 1_000 : startColumn + 1,
      message: error.message,
      severity: error.severity,
      code: error.error_code,
    })
  }
  return markers
}
