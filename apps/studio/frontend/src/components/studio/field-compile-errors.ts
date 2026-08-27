import type { CompileError, LintError } from "@/api/types"
import {
  fieldAxisCanNameARootNode,
  isSameDiagnosticFile,
  normalizeDiagnosticPath,
  rootPhaseIdFromPath,
} from "./diagnostic-paths"

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

// Root-anchored: `.workspace/` is Studio's workspace dir at the skill root; a nested
// occurrence would belong to a child skill, not to this graph's Input boundary.
const RUNTIME_INPUT_FILE_RE = /^\.workspace\/(?:import_files(?:\/|$)|runtime_config\.json$)/

function errorPhaseId(error: LintError): string | null {
  if (typeof error.phase_name === "string" && error.phase_name) {
    return error.phase_name
  }
  // Root-anchored: a diagnostic from inside a child skill names no root node
  // (see {@link import("./diagnostic-paths")}).
  return rootPhaseIdFromPath(error.file)
}

export function lintErrorsForPhase(
  errors: readonly LintError[] | null | undefined,
  phaseId: string,
): LintError[] {
  return (errors ?? []).filter((error) => {
    if (errorPhaseId(error) === phaseId) {
      return true
    }
    if (!fieldAxisCanNameARootNode(error?.file)) {
      return false
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
 * Select the field-grained diagnostics of whichever pass most recently
 * SETTLED for this skill instead of unioning manual Compile with lint
 * (ledger J-03.B) -- the Properties/input field-tooltip sibling of
 * {@link import("./node-compile-errors").selectActiveNodeErrors}. See that
 * function doc for why replacing (never merging) the two channels is
 * correct: a settled pass replaces the prior projection wholesale, so the
 * channel that did not just settle never contributes leftover diagnostics.
 */
export function selectActiveFieldErrors(
  source: "compile" | "lint",
  compileErrors: readonly CompileError[] | null | undefined,
  lintErrors: readonly LintError[] | null | undefined,
): LintError[] {
  return source === "compile" ? compileErrorsToFieldLintErrors(compileErrors) : [...(lintErrors ?? [])]
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
 * Matching is separator-insensitive equality: both sides are paths counted from the same
 * compile root, so nothing but the whole path identifies the file (see
 * {@link import("./diagnostic-paths")}). Errors with no `file` are skill-level and dropped.
 */
export function lintErrorsForFile(
  errors: readonly LintError[] | null | undefined,
  filePath: string,
): LintError[] {
  const target = normalizeDiagnosticPath(filePath)
  if (!target) {
    return []
  }
  return (errors ?? []).filter((error) => (
    typeof error?.file === "string" && !!error.file && isSameDiagnosticFile(error.file, target)
  ))
}

export type IoBoundary = "input" | "output"

function isInputBoundaryError(error: LintError): boolean {
  const file = typeof error.file === "string" ? normalizeDiagnosticPath(error.file) : ""
  if (RUNTIME_INPUT_FILE_RE.test(file)) {
    return true
  }
  if (!fieldAxisCanNameARootNode(error.file)) {
    return false
  }
  const field = error.field_path
  return field === "io.inputs" || (typeof field === "string" && field.startsWith("io.inputs."))
}

function isOutputBoundaryError(error: LintError): boolean {
  if (!fieldAxisCanNameARootNode(error.file)) {
    return false
  }
  const field = error.field_path
  return field === "io.outputs" || (typeof field === "string" && field.startsWith("io.outputs."))
}

export function lintErrorsForBoundary(
  errors: readonly LintError[] | null | undefined,
  boundary: IoBoundary,
): LintError[] {
  return (errors ?? []).filter((error) => (
    boundary === "input" ? isInputBoundaryError(error) : isOutputBoundaryError(error)
  ))
}

export function formatDiagnosticCode(code: string | null | undefined): string | null {
  const trimmed = code?.trim()
  if (!trimmed) {
    return null
  }
  return trimmed.startsWith("[") && trimmed.endsWith("]") ? trimmed : `[${trimmed}]`
}

function boundaryFieldKey(error: LintError, boundary: IoBoundary): string | null {
  const field = error.field_path?.trim()
  if (!field) {
    return null
  }
  const prefix = boundary === "input" ? "io.inputs.properties." : "io.outputs.properties."
  if (field.startsWith(prefix)) {
    const key = field.slice(prefix.length).split(".")[0]?.trim()
    return key || null
  }
  if (field === "io.inputs" || field === "io.outputs") {
    return null
  }
  if (field.startsWith("io.inputs.") || field.startsWith("io.outputs.")) {
    return null
  }
  const key = field.split(".")[0]?.trim()
  return key || null
}

export function boundaryFieldErrorsByKey(
  errors: readonly LintError[] | null | undefined,
  boundary: IoBoundary,
): Record<string, LintError[]> {
  const byField: Record<string, LintError[]> = {}
  for (const error of lintErrorsForBoundary(errors, boundary)) {
    const field = boundaryFieldKey(error, boundary)
    if (!field) {
      continue
    }
    const bucket = byField[field] ?? (byField[field] = [])
    bucket.push(error)
  }
  return byField
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
