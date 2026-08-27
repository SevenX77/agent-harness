import type { CompileError, LintError } from "@/api/types"
import { INPUT_ID, OUTPUT_ID } from "@/components/nodes"
import { fieldAxisCanNameARootNode, normalizeDiagnosticPath, rootPhaseIdFromPath } from "./diagnostic-paths"

const FIELD_NODE_PREFIX_RE = /^([A-Za-z0-9_-]+)\./
// Root-anchored like every other path read here: `.workspace/` is Studio's own workspace
// dir at the skill root, so a nested occurrence would belong to a child skill.
const RUNTIME_INPUT_FILE_RE = /^\.workspace\/(?:import_files(?:\/|$)|runtime_config\.json$)/

function boundaryNodeIdFromFile(file: string | null | undefined): string | null {
  if (typeof file !== "string") {
    return null
  }
  return RUNTIME_INPUT_FILE_RE.test(normalizeDiagnosticPath(file)) ? INPUT_ID : null
}

function boundaryNodeIdFromField(field: string | null | undefined): string | null {
  if (typeof field !== "string") {
    return null
  }
  if (field === "io.inputs" || field.startsWith("io.inputs.")) {
    return INPUT_ID
  }
  if (field === "io.outputs" || field.startsWith("io.outputs.")) {
    return OUTPUT_ID
  }
  return null
}

function compileErrorNodeId(error: CompileError | null | undefined): string | null {
  const file = error?.file
  const rootPhaseId = rootPhaseIdFromPath(file)
  if (rootPhaseId) {
    return rootPhaseId
  }
  const boundaryFromFile = boundaryNodeIdFromFile(file)
  if (boundaryFromFile) {
    return boundaryFromFile
  }
  if (!fieldAxisCanNameARootNode(file)) {
    return null
  }
  const field = error?.field
  const boundaryId = boundaryNodeIdFromField(field)
  if (boundaryId) {
    return boundaryId
  }
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

function lintErrorNodeId(error: LintError | null | undefined): string | null {
  const phaseName = error?.phase_name
  if (typeof phaseName === "string" && phaseName) {
    return phaseName
  }
  const file = error?.file
  const rootPhaseId = rootPhaseIdFromPath(file)
  if (rootPhaseId) {
    return rootPhaseId
  }
  const boundaryFromFile = boundaryNodeIdFromFile(file)
  if (boundaryFromFile) {
    return boundaryFromFile
  }
  if (!fieldAxisCanNameARootNode(file)) {
    return null
  }
  const field = error?.field_path
  const boundaryId = boundaryNodeIdFromField(field)
  if (boundaryId) {
    return boundaryId
  }
  if (typeof field === "string") {
    const fieldMatch = FIELD_NODE_PREFIX_RE.exec(field)
    if (fieldMatch) {
      return fieldMatch[1]
    }
  }
  return null
}

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

function lintErrorKey(error: LintError): string {
  return [
    error.file ?? "",
    error.line ?? "",
    error.field_path ?? "",
    error.error_code ?? "",
    error.severity,
    error.message,
  ].join("\u0000")
}

function uniqueLintErrors(errors: readonly LintError[]): LintError[] {
  const seen = new Set<string>()
  const unique: LintError[] = []
  for (const error of errors) {
    const key = lintErrorKey(error)
    if (seen.has(key)) {
      continue
    }
    seen.add(key)
    unique.push(error)
  }
  return unique
}

interface ActiveLintSources {
  firstScreenLint: readonly LintError[] | null | undefined
  manifestErrors: readonly LintError[] | null | undefined
  realtime: readonly LintError[] | null | undefined
}

export function activeLintErrors({ firstScreenLint, manifestErrors, realtime }: ActiveLintSources): LintError[] {
  if (realtime != null) {
    return uniqueLintErrors(realtime)
  }
  return uniqueLintErrors([...(firstScreenLint ?? []), ...(manifestErrors ?? [])])
}

/**
 * Select the node-grouped diagnostics of whichever pass most recently SETTLED
 * for this skill instead of unioning manual Compile with lint (ledger J-03.B).
 *
 * compile-lint F1/F6 + 03_compile.md A13: a settled pass (manual Compile, or
 * lint from typing / canvas-topology relint / an external skill_changed
 * relint) REPLACES the prior context-marker projection wholesale. The
 * channel that did not just settle is discarded even when it still holds
 * errors -- those errors may already be stale (e.g. fixed on disk by
 * whatever produced the fresher pass), and a stale + fresh union is exactly
 * the defect this replaces: a badge counting errors from two different
 * moments in time, and the same diagnostic appearing twice because the two
 * channels keyed it differently.
 */
export function selectActiveNodeErrors(
  source: "compile" | "lint",
  compileByNode: Record<string, CompileError[]>,
  lintByNode: Record<string, CompileError[]>,
): Record<string, CompileError[]> {
  return source === "compile" ? compileByNode : lintByNode
}
