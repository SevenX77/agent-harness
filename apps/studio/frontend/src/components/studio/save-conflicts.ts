import axios from "axios"
import type { SaveConflict } from "./WorkspaceContext"

export interface SaveRetryPayload {
  path: string
  content: string
  expectedHash: string
}

export interface HashConflictPayload {
  remoteContent: string
  remoteHash: string | null
}

export function overwriteRetryPayload(conflict: SaveConflict): SaveRetryPayload {
  if (!conflict.remoteHash) {
    throw new Error("Cannot retry overwrite without a remote hash")
  }
  return {
    path: conflict.path,
    content: conflict.localContent,
    expectedHash: conflict.remoteHash,
  }
}

export function conflictFromSaveError(error: unknown, current: SaveConflict): SaveConflict | null {
  const payload = hashConflictPayloadFromSaveError(error)
  if (payload) {
    return {
      ...current,
      remoteContent: payload.remoteContent,
      remoteHash: payload.remoteHash,
    }
  }
  return null
}

export function hashConflictPayloadFromSaveError(error: unknown): HashConflictPayload | null {
  if (isTauriHashConflictError(error)) {
    return {
      remoteContent: error.data?.current_content ?? "",
      remoteHash: error.data?.current_hash ?? null,
    }
  }
  if (!axios.isAxiosError(error) || error.response?.status !== 409) {
    return null
  }
  const data = error.response.data as {
    current_hash?: string
    current_markdown_content?: string
  }
  return {
    remoteContent: data.current_markdown_content ?? "",
    remoteHash: data.current_hash ?? null,
  }
}

export function isSameSaveConflict(
  current: SaveConflict | null,
  handled: SaveConflict,
): boolean {
  return Boolean(
    current &&
    current.skillId === handled.skillId &&
    current.path === handled.path &&
    current.side === handled.side &&
    current.remoteHash === handled.remoteHash,
  )
}

interface TauriHashConflictError {
  type: "HashConflict"
  data?: {
    current_hash?: string
    current_content?: string
  }
}

function isTauriHashConflictError(error: unknown): error is TauriHashConflictError {
  return (
    typeof error === "object" &&
    error !== null &&
    "type" in error &&
    error.type === "HashConflict"
  )
}
