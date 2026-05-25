import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import {
  putRegistryEndpoints,
  type CredentialRegistryResponse,
  type ProviderEndpoint,
} from "@/api/llm"

/** Status of the most recent (or in-flight) auto-save call. */
export type SaveStatus = "idle" | "pending" | "saving" | "saved" | "error"

export interface UseDebouncedCredentialsSaveOptions {
  /** Milliseconds to wait after the last `queue()` call. Default 300. */
  delayMs?: number
  /** Replace the API call (for unit tests). */
  putFn?: (updates: Record<string, ProviderEndpoint>) => Promise<CredentialRegistryResponse>
  /** Receive the server's registry response on success. */
  onSaved?: (next: CredentialRegistryResponse) => void
  /** Receive the underlying error on failure. */
  onError?: (error: unknown) => void
}

export interface UseDebouncedCredentialsSaveResult {
  /**
   * Schedule a save. Each call resets the debounce timer; the eventual endpoint
   * upsert body is built from `buildEndpointUpsertPayload(getSnapshot())` so
   * that intermediate keystrokes coalesce into one network request.
   */
  queue: (getEndpointsSnapshot: () => ProviderEndpoint[]) => void
  /** Cancel any pending save (no network call). */
  cancel: () => void
  /** Force a save now (still serialized through the same flight). */
  flush: () => Promise<CredentialRegistryResponse | null>
  status: SaveStatus
  lastError: unknown
}

/**
 * Debounced auto-save for endpoint registry edits.
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
  const { delayMs = 300, putFn = putRegistryEndpoints, onSaved, onError } = options
  const [status, setStatus] = useState<SaveStatus>("idle")
  const [lastError, setLastError] = useState<unknown>(null)

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inflightRef = useRef<Promise<CredentialRegistryResponse | null> | null>(null)
  const pendingSnapshotRef = useRef<(() => ProviderEndpoint[]) | null>(null)

  const performSave = useCallback(
    // eslint-disable-next-line react-hooks/preserve-manual-memoization
    async (getSnapshot: () => ProviderEndpoint[]): Promise<CredentialRegistryResponse | null> => {
      setStatus("saving")
      const payload = buildEndpointUpsertPayload(getSnapshot())
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
        toast.error(`Endpoints save failed: ${message}`)
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
    (getSnapshot: () => ProviderEndpoint[]) => {
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

  const flush = useCallback(async (): Promise<CredentialRegistryResponse | null> => {
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
 * Build an endpoint upsert request body from the current draft state.
 *
 * Critical: only fields accepted by the backend endpoint upsert are forwarded.
 * Route/test outcome fields are backend-owned and rejected in PUT bodies.
 */
export function buildEndpointUpsertPayload(
  providers: ReadonlyArray<{
    endpoint_id: string
    display_name: string
    protocol: ProviderEndpoint["protocol"]
    base_url?: string
    api_key?: string | null
    status?: ProviderEndpoint["status"]
    timeout_seconds?: number
    trust_env?: boolean
    proxy_env?: string | null
    metadata?: Record<string, unknown>
  }>,
): Record<string, ProviderEndpoint> {
  return Object.fromEntries(
    providers.map((provider) => [
      provider.endpoint_id,
      {
        endpoint_id: provider.endpoint_id,
        display_name: provider.display_name,
        protocol: provider.protocol,
        base_url: provider.base_url ?? "",
        api_key: provider.api_key ?? null,
        status: provider.status ?? "unverified_manual",
        timeout_seconds: provider.timeout_seconds ?? 60,
        trust_env: provider.trust_env ?? false,
        proxy_env: provider.proxy_env ?? null,
        metadata: provider.metadata ?? {},
      },
    ]),
  )
}
