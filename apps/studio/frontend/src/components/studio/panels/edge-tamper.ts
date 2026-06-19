import type { ResumeRunOptions } from '@/api/client'
import type { JsonObject } from '@/api/types'
import type { SelectedEdge } from '../WorkspaceContext'

export type EdgeTamperResumeResult =
  | { ok: true; options: ResumeRunOptions }
  | { ok: false; error: string }

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

export function edgeTamperResumeOptionsFromJson(
  selectedEdge: SelectedEdge,
  rawJson: string,
): EdgeTamperResumeResult {
  let contextOverrides: JsonObject | null
  try {
    contextOverrides = parseJsonObject(rawJson)
  } catch {
    return { ok: false, error: 'Invalid JSON: fix the edited context before resuming downstream.' }
  }
  if (contextOverrides === null) {
    return { ok: false, error: 'Invalid JSON: edge context overrides must be a JSON object.' }
  }

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
