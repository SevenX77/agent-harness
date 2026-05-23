import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import {
  putCredentials,
  type CredentialsState,
  type ProviderCredentialUpdate,
} from "@/api/llm"

/** Status of the most recent (or in-flight) auto-save call. */
export type SaveStatus = "idle" | "pending" | "saving" | "saved" | "error"

export interface UseDebouncedCredentialsSaveOptions {
  /** Milliseconds to wait after the last `queue()` call. Default 300. */
  delayMs?: number
  /** Replace the API call (for unit tests). */
  putFn?: (updates: ProviderCredentialUpdate[]) => Promise<CredentialsState>
  /** Receive the server's CredentialsState response on success. */
  onSaved?: (next: CredentialsState) => void
  /** Receive the underlying error on failure. */
  onError?: (error: unknown) => void
}

export interface UseDebouncedCredentialsSaveResult {
  /**
   * Schedule a save. Each call resets the debounce timer; the eventual PUT
   * body is built from `buildPutPayload(getProvidersSnapshot())` so that
   * intermediate keystrokes coalesce into one network request.
   */
  queue: (getProvidersSnapshot: () => ProviderCredentialUpdate[]) => void
  /** Cancel any pending save (no network call). */
  cancel: () => void
  /** Force a save now (still serialized through the same flight). */
  flush: () => Promise<CredentialsState | null>
  status: SaveStatus
  lastError: unknown
}

/**
 * Debounced auto-save for the API Keys page (spec F2).
 *
 * Coalescing rule: every call to `queue()` resets a 300ms timer. When the
 * timer fires, the latest `getProvidersSnapshot()` is consulted *at fire
 * time* — that gives us the freshest draft state without re-binding the
 * timer on every keystroke.
 *
 * Concurrency rule: while a PUT is in flight (`status === 'saving'`), a new
 * `queue()` call buffers the latest snapshot getter. After the current call
 * resolves, the buffered snapshot is dispatched in a new PUT. This prevents
 * Test-writeback races from racing in-flight credential PUTs.
 */
export function useDebouncedCredentialsSave(
  options: UseDebouncedCredentialsSaveOptions = {},
): UseDebouncedCredentialsSaveResult {
  const { delayMs = 300, putFn = putCredentials, onSaved, onError } = options
  const [status, setStatus] = useState<SaveStatus>("idle")
  const [lastError, setLastError] = useState<unknown>(null)

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inflightRef = useRef<Promise<CredentialsState | null> | null>(null)
  const pendingSnapshotRef = useRef<(() => ProviderCredentialUpdate[]) | null>(null)

  const performSave = useCallback(
    // eslint-disable-next-line react-hooks/preserve-manual-memoization
    async (getSnapshot: () => ProviderCredentialUpdate[]): Promise<CredentialsState | null> => {
      setStatus("saving")
      const payload = getSnapshot()
      try {
        const next = await putFn(payload)
        setStatus("saved")
        setLastError(null)
        onSaved?.(next)
        return next
      } catch (error) {
        setStatus("error")
        setLastError(error)
        const message = error instanceof Error ? error.message : "Save failed"
        toast.error(`API Keys save failed: ${message}`)
        onError?.(error)
        return null
      } finally {
        inflightRef.current = null
        // If something queued while we were saving, fire the next one now.
        const buffered = pendingSnapshotRef.current
        if (buffered) {
          pendingSnapshotRef.current = null
          inflightRef.current = performSave(buffered)
        }
      }
    },
    [putFn, onSaved, onError],
  )

  const queue = useCallback(
    (getSnapshot: () => ProviderCredentialUpdate[]) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      setStatus("pending")
      timerRef.current = setTimeout(() => {
        timerRef.current = null
        if (inflightRef.current) {
          // A save is currently in flight — defer until it resolves.
          pendingSnapshotRef.current = getSnapshot
          return
        }
        inflightRef.current = performSave(getSnapshot)
      }, delayMs)
    },
    [delayMs, performSave],
  )

  const cancel = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    pendingSnapshotRef.current = null
    setStatus((prev) => (prev === "pending" ? "idle" : prev))
  }, [])

  const flush = useCallback(async (): Promise<CredentialsState | null> => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    if (inflightRef.current) return inflightRef.current
    const snapshot = pendingSnapshotRef.current
    if (!snapshot) return null
    pendingSnapshotRef.current = null
    inflightRef.current = performSave(snapshot)
    return inflightRef.current
  }, [performSave])

  // Cleanup on unmount: drop the timer, but let any in-flight PUT settle on
  // the server (no abort signal — partial credential writes would leave the
  // user in a worse state than letting it land).
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = null
      pendingSnapshotRef.current = null
    }
  }, [])

  return { queue, cancel, flush, status, lastError }
}

/**
 * Build a PUT request body from the current draft state.
 *
 * Critical: only the fields accepted by `ProviderCredentialWrite` on the
 * backend are forwarded. Test outcome fields (`last_test_*`,
 * `available_sdks`, `available_models`) are *single-writer* — the backend
 * rejects them in PUT bodies with 422.
 */
export function buildPutPayload(
  providers: ReadonlyArray<{
    id: string
    name: string
    api_key?: string
    base_url?: string
    provider_type?: ProviderCredentialUpdate["provider_type"]
  }>,
): ProviderCredentialUpdate[] {
  return providers.map((provider) => ({
    id: provider.id,
    name: provider.name,
    api_key: provider.api_key ?? "",
    base_url: provider.base_url ?? "",
    provider_type: provider.provider_type ?? null,
  }))
}
