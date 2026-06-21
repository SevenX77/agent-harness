import { useCallback, useEffect, useState } from 'react'
import { workspacePathExists } from '../lib/tauri'
import { errorMessage } from '../utils/errors'

export interface RecentWorkspaceEntry {
  absolutePath: string
  displayName: string
  identity: string
  lastOpenedAt: string
}

export interface RecentWorkspacesReadResult {
  entries: RecentWorkspaceEntry[]
  error: string | null
}

/**
 * Read the localStorage MRU, surfacing any read/parse failure instead of
 * swallowing it (N1 atom #9 + zero-silent-failure). A corrupt blob or a
 * blocked/throwing localStorage degrades `entries` to [] AND reports a non-null
 * `error` so Home can render the local red-box fallback over the still-usable
 * New/Open entries. The failure is logged at WARN — never silently dropped.
 */
export function readRecentWorkspacesResult(): RecentWorkspacesReadResult {
  if (typeof window === 'undefined') {
    return { entries: [], error: null }
  }
  try {
    const parsed = JSON.parse(localStorage.getItem('recentWorkspaces') || '[]') as unknown
    const entries = Array.isArray(parsed) ? parsed.filter((w): w is RecentWorkspaceEntry => (
      w && typeof w === 'object' && 'absolutePath' in w && 'displayName' in w && 'identity' in w
    )) : []
    return { entries, error: null }
  } catch (error) {
    const reason = errorMessage(error)
    console.warn('phase=recent-skills action=read-failed reason=%s', reason)
    return { entries: [], error: reason }
  }
}

export function readRecentWorkspaces(): RecentWorkspaceEntry[] {
  return readRecentWorkspacesResult().entries
}

export function rememberRecentWorkspace(workspace: Pick<RecentWorkspaceEntry, 'absolutePath' | 'displayName'>): RecentWorkspaceEntry {
  const absolutePath = workspace.absolutePath
  const displayName = workspace.displayName
  const identity = `local:${absolutePath}`
  const lastOpenedAt = new Date().toISOString()

  const entry: RecentWorkspaceEntry = {
    absolutePath,
    displayName,
    identity,
    lastOpenedAt,
  }

  if (typeof window !== 'undefined') {
    const list = readRecentWorkspaces()
    const filtered = list.filter((w) => w.identity !== identity)
    const next = [entry, ...filtered].slice(0, 10)
    localStorage.setItem('recentWorkspaces', JSON.stringify(next))
  }

  return entry
}

export function removeRecentWorkspace(identity: string): void {
  if (typeof window === 'undefined') return
  const list = readRecentWorkspaces()
  const next = list.filter((w) => w.identity !== identity)
  localStorage.setItem('recentWorkspaces', JSON.stringify(next))
}

export function pruneMissingRecentWorkspaces(exists: (absolutePath: string) => boolean): RecentWorkspaceEntry[] {
  if (typeof window === 'undefined') return []
  const list = readRecentWorkspaces()
  const next = list.filter((w) => exists(w.absolutePath))
  localStorage.setItem('recentWorkspaces', JSON.stringify(next))
  return next
}

/**
 * Async stale-MRU prune (R1 / N1 #6): drop Recent entries whose folder no longer
 * exists on disk. The existence predicate is the Rust `workspace_path_exists`
 * native-fs check (via lib/tauri.workspacePathExists), which degrades to `true`
 * outside the desktop runtime so a web session never prunes its localStorage MRU.
 * Keeps the localStorage write semantics of the sync variant.
 */
export async function pruneMissingRecentWorkspacesAsync(
  exists: (absolutePath: string) => Promise<boolean> = workspacePathExists,
): Promise<RecentWorkspaceEntry[]> {
  if (typeof window === 'undefined') return []
  const list = readRecentWorkspaces()
  const flags = await Promise.all(list.map((w) => exists(w.absolutePath)))
  const next = list.filter((_, index) => flags[index])
  if (next.length !== list.length) {
    localStorage.setItem('recentWorkspaces', JSON.stringify(next))
  }
  return next
}

export function useRecentSkills() {
  const initial = readRecentWorkspacesResult()
  const [recentWorkspaces, setRecentWorkspaces] = useState<RecentWorkspaceEntry[]>(initial.entries)
  // N1 atom #9: local error fallback. Holds the MRU read / path-validation
  // failure reason so Home renders a local red box (over the still-usable
  // New/Open entries) instead of silently swallowing the failure.
  const [recentError, setRecentError] = useState<string | null>(initial.error)
  // Cold-start window: true for the first paint before the client has confirmed
  // the localStorage MRU read. Home shows a Recent skeleton while this is true so
  // the cold-start / pre-hydration moment is a placeholder, not a blank flash (D6).
  const [isHydrating, setIsHydrating] = useState(true)

  useEffect(() => {
    let cancelled = false
    const read = readRecentWorkspacesResult()
    setRecentWorkspaces(read.entries)
    setRecentError(read.error)
    setIsHydrating(false)
    // R1 (N1 #6): on cold start, drop Recent cards whose folder is gone. The
    // existence check is the Rust native-fs `workspace_path_exists` (web degrades
    // to keep-all), so a missing folder is pruned from the MRU before the user
    // clicks a dead card. A prune (path-validation) failure is non-fatal for the
    // entries — the unpruned MRU still renders — but it is surfaced as the local
    // error and logged, never silently swallowed (atom #9 / zero-silent-failure).
    pruneMissingRecentWorkspacesAsync()
      .then((pruned) => {
        if (!cancelled) {
          setRecentWorkspaces(pruned)
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return
        }
        const reason = errorMessage(error)
        console.warn('phase=recent-skills action=prune-failed reason=%s', reason)
        setRecentError(reason)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const rememberWorkspace = useCallback((workspace: Pick<RecentWorkspaceEntry, 'absolutePath' | 'displayName'>) => {
    const entry = rememberRecentWorkspace(workspace)
    setRecentWorkspaces(readRecentWorkspaces())
    return entry
  }, [])

  const removeWorkspace = useCallback((identity: string) => {
    removeRecentWorkspace(identity)
    setRecentWorkspaces(readRecentWorkspaces())
  }, [])

  return {
    recentWorkspaces,
    rememberWorkspace,
    removeWorkspace,
    isHydrating,
    recentError,
  }
}
