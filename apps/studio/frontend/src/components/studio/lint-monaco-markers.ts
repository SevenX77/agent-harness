import type { LintResult } from "@/api/types"
import type { MonacoApi, MonacoEditor } from "@/components/MonacoPanel"
import { lintErrorsToMarkers, type LintMarkerDescriptor } from "./field-compile-errors"

/**
 * Monaco runtime adapter for IDE-style inline lint markers (authoring N3 atom #6).
 *
 * Keeps the marker math pure in {@link lintErrorsToMarkers} and confines the monaco
 * dependency here: translate the engine's string severity to {@link MarkerSeverity} and
 * push the markers onto the editor model under a dedicated owner so they replace cleanly
 * each lint cycle (an empty list clears stale markers). Source of truth stays the engine
 * lint payload — this never invents diagnostics or lines.
 */

export const LINT_MARKER_OWNER = "studio-lint"

type ModelMarkerData = Parameters<MonacoApi["editor"]["setModelMarkers"]>[2][number]
type TextModel = Parameters<MonacoApi["editor"]["setModelMarkers"]>[0]

function toMarkerSeverity(
  monaco: MonacoApi,
  severity: LintMarkerDescriptor["severity"],
): ModelMarkerData["severity"] {
  return severity === "warning"
    ? monaco.MarkerSeverity.Warning
    : monaco.MarkerSeverity.Error
}

/**
 * Replace the lint markers on `model` with the line-bearing diagnostics from `lintResult`.
 *
 * No-ops when monaco/model are unavailable (editor not mounted yet); a null/empty result
 * clears the owner's markers. Line-less diagnostics are dropped upstream by
 * {@link lintErrorsToMarkers} and surface only in the file-level diagnostics strip.
 */
export function applyLintMarkers(
  monaco: MonacoApi | null,
  model: ReturnType<MonacoEditor["getModel"]> | null,
  lintResult: LintResult | null,
): void {
  if (!monaco || !model) {
    return
  }
  const markers: ModelMarkerData[] = lintErrorsToMarkers(lintResult?.errors).map((marker) => ({
    startLineNumber: marker.startLineNumber,
    endLineNumber: marker.endLineNumber,
    startColumn: marker.startColumn,
    endColumn: marker.endColumn,
    message: marker.message,
    severity: toMarkerSeverity(monaco, marker.severity),
    code: marker.code,
  }))
  monaco.editor.setModelMarkers(model as TextModel, LINT_MARKER_OWNER, markers)
}
