import { describe, expect, it } from "vitest"
import { AxiosError } from "axios"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"
import {
  conflictFromSaveError,
  hashConflictPayloadFromSaveError,
  isSameSaveConflict,
  overwriteRetryPayload,
} from "./save-conflicts"
import type { SaveConflict } from "./WorkspaceContext"

function buildConflict(overrides: Partial<SaveConflict> = {}): SaveConflict {
  return {
    skillId: "writer-smoke",
    path: "phases/draft/SKILL.md",
    side: "left",
    localContent: "local draft\n",
    remoteContent: "remote draft\n",
    remoteHash: "remote-hash",
    ...overrides,
  }
}

describe("overwriteRetryPayload", () => {
  it("uses the local draft with the remote hash as the next expectedHash", () => {
    expect(overwriteRetryPayload(buildConflict())).toEqual({
      path: "phases/draft/SKILL.md",
      content: "local draft\n",
      expectedHash: "remote-hash",
    })
  })

  it("does not retry as an unguarded overwrite when the remote hash is missing", () => {
    expect(() => overwriteRetryPayload(buildConflict({ remoteHash: null }))).toThrow(
      /remote hash/i,
    )
  })
})

describe("conflictFromSaveError", () => {
  it("refreshes the conflict from a second hash-conflict response", () => {
    const current = buildConflict({ remoteHash: "first-remote-hash" })

    expect(conflictFromSaveError(hashConflictError({
      current_hash: "second-remote-hash",
      current_markdown_content: "second remote\n",
    }), current)).toEqual({
      ...current,
      remoteHash: "second-remote-hash",
      remoteContent: "second remote\n",
    })
  })

  it("refreshes the conflict from a Tauri native HashConflict error", () => {
    const current = buildConflict({ remoteHash: "first-remote-hash" })

    expect(conflictFromSaveError({
      type: "HashConflict",
      data: {
        current_hash: "tauri-remote-hash",
        current_content: "tauri remote\n",
      },
    }, current)).toEqual({
      ...current,
      remoteHash: "tauri-remote-hash",
      remoteContent: "tauri remote\n",
    })
  })

  it("extracts a reusable conflict payload without a workspace conflict shell", () => {
    expect(hashConflictPayloadFromSaveError({
      type: "HashConflict",
      data: {
        current_hash: "remote-hash",
        current_content: "remote body\n",
      },
    })).toEqual({
      remoteHash: "remote-hash",
      remoteContent: "remote body\n",
    })
  })

  it("ignores non-conflict save errors", () => {
    expect(conflictFromSaveError(new Error("network down"), buildConflict())).toBeNull()
    expect(hashConflictPayloadFromSaveError(new Error("network down"))).toBeNull()
  })
})

describe("isSameSaveConflict", () => {
  it("matches only the conflict that started the overwrite retry", () => {
    const current = buildConflict()

    expect(isSameSaveConflict(current, buildConflict())).toBe(true)
    expect(isSameSaveConflict(current, buildConflict({ remoteHash: "newer-remote-hash" }))).toBe(false)
    expect(isSameSaveConflict(current, buildConflict({ path: "GRAPH.md" }))).toBe(false)
    expect(isSameSaveConflict(null, current)).toBe(false)
  })
})

function hashConflictError(data: Record<string, unknown>): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig
  const response: AxiosResponse = {
    data,
    status: 409,
    statusText: "Conflict",
    headers: {},
    config,
  }
  return new AxiosError("Hash conflict", "ERR_BAD_RESPONSE", config, null, response)
}
