import type { CompileError, LintError } from "@/api/types"

const PHASE_FILE_RE = /(?:^|\/)phases\/([A-Za-z0-9_-]+)\//
const FIELD_NODE_PREFIX_RE = /^([A-Za-z0-9_-]+)\./

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

function compileErrorKey(error: CompileError): string {
  return [
    error.file ?? "",
    error.line ?? "",
    error.field ?? "",
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

function pushUniqueCompileError(bucket: CompileError[], seen: Set<string>, error: CompileError): void {
  const key = compileErrorKey(error)
  if (seen.has(key)) {
    return
  }
  seen.add(key)
  bucket.push(error)
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
 * Merge node diagnostics from the two engine-backed channels:
 * manual Compile and first-screen/realtime lint.
 *
 * Missing blackboard supply is not synthesized from graph_topology.field_supply
 * here. It must arrive as an engine compile/lint diagnostic so the canvas,
 * editor, properties panel, and Compile drawer all project the same source.
 */
export function mergeNodeErrors(
  compileByNode: Record<string, CompileError[]>,
  lintByNode: Record<string, CompileError[]>,
): Record<string, CompileError[]> {
  const merged: Record<string, CompileError[]> = {}
  const seenByNode: Record<string, Set<string>> = {}
  for (const [nodeId, errors] of Object.entries(compileByNode)) {
    const bucket = merged[nodeId] ?? (merged[nodeId] = [])
    const seen = seenByNode[nodeId] ?? (seenByNode[nodeId] = new Set())
    for (const error of errors) {
      pushUniqueCompileError(bucket, seen, error)
    }
  }
  for (const [nodeId, errors] of Object.entries(lintByNode)) {
    const bucket = merged[nodeId] ?? (merged[nodeId] = [])
    const seen = seenByNode[nodeId] ?? (seenByNode[nodeId] = new Set())
    for (const error of errors) {
      pushUniqueCompileError(bucket, seen, error)
    }
  }
  return merged
}
