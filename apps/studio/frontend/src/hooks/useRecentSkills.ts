import { useCallback, useEffect, useState } from 'react'
import { workspacePathExists } from '../lib/tauri'

export interface RecentWorkspaceEntry {
  absolutePath: string
  displayName: string
  identity: string
  lastOpenedAt: string
}

export function readRecentWorkspaces(): RecentWorkspaceEntry[] {
  if (typeof window === 'undefined') {
    return []
  }
  try {
    const parsed = JSON.parse(localStorage.getItem('recentWorkspaces') || '[]') as unknown
    return Array.isArray(parsed) ? parsed.filter((w): w is RecentWorkspaceEntry => (
      w && typeof w === 'object' && 'absolutePath' in w && 'displayName' in w && 'identity' in w
    )) : []
  } catch {
    return []
  }
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
  const [recentWorkspaces, setRecentWorkspaces] = useState<RecentWorkspaceEntry[]>(() => {
    return readRecentWorkspaces()
  })
  // Cold-start window: true for the first paint before the client has confirmed
  // the localStorage MRU read. Home shows a Recent skeleton while this is true so
  // the cold-start / pre-hydration moment is a placeholder, not a blank flash (D6).
  const [isHydrating, setIsHydrating] = useState(true)

  useEffect(() => {
    let cancelled = false
    setRecentWorkspaces(readRecentWorkspaces())
    setIsHydrating(false)
    // R1 (N1 #6): on cold start, drop Recent cards whose folder is gone. The
    // existence check is the Rust native-fs `workspace_path_exists` (web degrades
    // to keep-all), so a missing folder is pruned from the MRU before the user
    // clicks a dead card. Failures here are non-fatal — the unpruned MRU still
    // renders.
    pruneMissingRecentWorkspacesAsync()
      .then((pruned) => {
        if (!cancelled) {
          setRecentWorkspaces(pruned)
        }
      })
      .catch(() => undefined)
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
  }
}
