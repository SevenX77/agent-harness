import type { ResumeRunOptions } from '@/api/client'
import type { JsonObject } from '@/api/types'
import type { SelectedEdge } from '../WorkspaceContext'

export type EdgeTamperResumeResult =
  | { ok: true; options: ResumeRunOptions }
  | { ok: false; error: string }

export type EdgeTamperJsonValidation =
  | { ok: true }
  | { ok: false; error: string }

const INVALID_JSON_SYNTAX = 'Invalid JSON: fix the edited context before resuming downstream.'
const INVALID_JSON_SHAPE = 'Invalid JSON: edge context overrides must be a JSON object.'

function stringField(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() !== '' ? value : undefined
}

function parseJsonObject(rawJson: string): JsonObject | null {
  const parsed = JSON.parse(rawJson) as unknown
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return null
  }
  return parsed as JsonObject
}

/**
 * Pure JSON-shape check for the writable tamper editor's live validity indicator.
 *
 * The editor reuses the read-only trace surface switched writable (F6 / Q3), so it
 * needs the SAME accept/reject contract the resume request uses — a tampered
 * context must parse AND be a plain JSON object. Kept separate from
 * `edgeTamperResumeOptionsFromJson` so the editor can render validity on every
 * keystroke without building a full resume payload, and so both share one rule set.
 */
export function validateTamperJson(rawJson: string): EdgeTamperJsonValidation {
  let parsed: JsonObject | null
  try {
    parsed = parseJsonObject(rawJson)
  } catch {
    return { ok: false, error: INVALID_JSON_SYNTAX }
  }
  if (parsed === null) {
    return { ok: false, error: INVALID_JSON_SHAPE }
  }
  return { ok: true }
}

export function edgeTamperResumeOptionsFromJson(
  selectedEdge: SelectedEdge,
  rawJson: string,
): EdgeTamperResumeResult {
  const validation = validateTamperJson(rawJson)
  if (!validation.ok) {
    return { ok: false, error: validation.error }
  }
  // Already validated above as a plain JSON object; parse once more for the value.
  const contextOverrides = parseJsonObject(rawJson) as JsonObject

  const context = selectedEdge.contextJson ?? {}
  return {
    ok: true,
    options: {
      checkpointId: stringField(context.checkpoint_id),
      checkpointNs: stringField(context.checkpoint_ns),
      resumeFromNodeId: selectedEdge.target,
      contextOverrides,
    },
  }
}
