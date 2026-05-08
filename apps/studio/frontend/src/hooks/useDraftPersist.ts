import { useCallback, useEffect, useMemo, useState } from 'react'

const DRAFT_PREFIX = 'studio:draft:'
const DRAFT_TTL_MS = 7 * 24 * 60 * 60 * 1000

export interface StoredDraft {
  content: string
  timestamp: number
  baseHash: string
}

interface UseDraftPersistConfig {
  skillId: string | null
  content: string
  baseContent: string
  dirty: boolean
  debounceMs?: number
}

export function draftStorageKey(skillId: string): string {
  return `${DRAFT_PREFIX}${skillId}`
}

export function hashDraftBase(content: string): string {
  let hash = 0
  for (let index = 0; index < content.length; index += 1) {
    hash = ((hash << 5) - hash + content.charCodeAt(index)) | 0
  }
  return hash.toString(16)
}

export function readStoredDraft(skillId: string): StoredDraft | null {
  try {
    const raw = window.localStorage.getItem(draftStorageKey(skillId))
    if (!raw) {
      return null
    }
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return null
    }
    const record = parsed as Partial<StoredDraft>
    if (typeof record.content !== 'string' || typeof record.timestamp !== 'number' || typeof record.baseHash !== 'string') {
      return null
    }
    return {
      content: record.content,
      timestamp: record.timestamp,
      baseHash: record.baseHash,
    }
  } catch {
    return null
  }
}

export function hasStoredDraft(skillId: string): boolean {
  return readStoredDraft(skillId) !== null
}

export function cleanupExpiredDrafts(now = Date.now()): void {
  try {
    for (let index = window.localStorage.length - 1; index >= 0; index -= 1) {
      const key = window.localStorage.key(index)
      if (!key?.startsWith(DRAFT_PREFIX)) {
        continue
      }
      const skillId = key.slice(DRAFT_PREFIX.length)
      const draft = readStoredDraft(skillId)
      if (!draft || now - draft.timestamp > DRAFT_TTL_MS) {
        window.localStorage.removeItem(key)
      }
    }
  } catch {
    // Best-effort cleanup; storage may be unavailable in private contexts.
  }
}

export function useDraftPersist({
  skillId,
  content,
  baseContent,
  dirty,
  debounceMs = 1000,
}: UseDraftPersistConfig) {
  const [draft, setDraft] = useState<StoredDraft | null>(null)
  const baseHash = useMemo(() => hashDraftBase(baseContent), [baseContent])

  const refreshDraft = useCallback(() => {
    setDraft(skillId ? readStoredDraft(skillId) : null)
  }, [skillId])

  const restoreDraft = useCallback(() => (
    skillId ? readStoredDraft(skillId) : null
  ), [skillId])

  const clearDraft = useCallback(() => {
    if (!skillId) {
      return
    }
    window.localStorage.removeItem(draftStorageKey(skillId))
    setDraft(null)
  }, [skillId])

  const hasDraft = useCallback(() => (
    skillId ? hasStoredDraft(skillId) : false
  ), [skillId])

  useEffect(() => {
    cleanupExpiredDrafts()
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshDraft()
  }, [refreshDraft])

  useEffect(() => {
    if (!skillId || !dirty) {
      return undefined
    }
    const timeout = window.setTimeout(() => {
      const nextDraft: StoredDraft = {
        content,
        timestamp: Date.now(),
        baseHash,
      }
      try {
        window.localStorage.setItem(draftStorageKey(skillId), JSON.stringify(nextDraft))
        setDraft(nextDraft)
      } catch {
        // Storage quota or browser privacy settings should not interrupt editing.
      }
    }, debounceMs)

    return () => window.clearTimeout(timeout)
  }, [baseHash, content, debounceMs, dirty, skillId])

  return {
    isDirty: dirty,
    draft,
    baseHash,
    restoreDraft,
    clearDraft,
    hasDraft,
    refreshDraft,
  }
}
