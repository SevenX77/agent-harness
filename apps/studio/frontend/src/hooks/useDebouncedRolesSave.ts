import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { putRoles, type RolesData } from "@/api/llm"
import type { SaveStatus } from "./useDebouncedCredentialsSave"

export interface UseDebouncedRolesSaveOptions {
  delayMs?: number
  putFn?: (data: RolesData) => Promise<RolesData>
  onSaved?: (next: RolesData) => void
  onError?: (error: unknown) => void
}

export interface UseDebouncedRolesSaveResult {
  queue: (getSnapshot: () => RolesData | null) => void
  cancel: () => void
  flush: () => Promise<RolesData | null>
  status: SaveStatus
  lastError: unknown
}

export function useDebouncedRolesSave(
  options: UseDebouncedRolesSaveOptions = {},
): UseDebouncedRolesSaveResult {
  const { delayMs = 300, putFn = putRoles, onSaved, onError } = options
  const [status, setStatus] = useState<SaveStatus>("idle")
  const [lastError, setLastError] = useState<unknown>(null)

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inflightRef = useRef<Promise<RolesData | null> | null>(null)
  const pendingSnapshotRef = useRef<(() => RolesData | null) | null>(null)

  const performSave = useCallback(
    // eslint-disable-next-line react-hooks/preserve-manual-memoization
    async (getSnapshot: () => RolesData | null): Promise<RolesData | null> => {
      const payload = getSnapshot()
      if (!payload) return null
      setStatus("saving")
      try {
        const next = await putFn(payload)
        const hasBufferedSave = Boolean(pendingSnapshotRef.current)
        if (!hasBufferedSave) {
          setStatus("saved")
          setLastError(null)
          onSaved?.(next)
        }
        return next
      } catch (error) {
        const hasBufferedSave = Boolean(pendingSnapshotRef.current)
        if (!hasBufferedSave) {
          setStatus("error")
          setLastError(error)
          const message = error instanceof Error ? error.message : "Save failed"
          toast.error(`LLM Roles save failed: ${message}`)
          onError?.(error)
        }
        return null
      } finally {
        inflightRef.current = null
        const buffered = pendingSnapshotRef.current
        if (buffered) {
          pendingSnapshotRef.current = null
          inflightRef.current = performSave(buffered)
        }
      }
    },
    [onError, onSaved, putFn],
  )

  const queue = useCallback(
    (getSnapshot: () => RolesData | null) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      setStatus("pending")
      if (inflightRef.current) {
        pendingSnapshotRef.current = getSnapshot
        return
      }
      timerRef.current = setTimeout(() => {
        timerRef.current = null
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

  const flush = useCallback(async (): Promise<RolesData | null> => {
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

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = null
      pendingSnapshotRef.current = null
    }
  }, [])

  return { queue, cancel, flush, status, lastError }
}
