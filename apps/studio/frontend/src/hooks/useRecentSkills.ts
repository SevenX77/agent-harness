import { useCallback, useEffect, useState } from 'react'

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

export function useRecentSkills() {
  const [recentWorkspaces, setRecentWorkspaces] = useState<RecentWorkspaceEntry[]>(() => {
    return readRecentWorkspaces()
  })
  // Cold-start window: true for the first paint before the client has confirmed
  // the localStorage MRU read. Home shows a Recent skeleton while this is true so
  // the cold-start / pre-hydration moment is a placeholder, not a blank flash (D6).
  const [isHydrating, setIsHydrating] = useState(true)

  useEffect(() => {
    setRecentWorkspaces(readRecentWorkspaces())
    setIsHydrating(false)
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
