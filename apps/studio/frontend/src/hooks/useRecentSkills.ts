import { useCallback, useEffect, useState } from 'react'
import {
  addRecentWorkspace,
  listRecentWorkspaces,
  removeRecentWorkspace as removeRecentWorkspaceNative,
  workspacePathExists,
} from '../lib/tauri'
import { errorMessage } from '../utils/errors'

export interface RecentWorkspaceEntry {
  absolutePath: string
  displayName: string
  identity: string
  lastOpenedAt: string
}

/** MRU cap — Home shows at most this many recent skills, most-recent first. */
export const RECENT_CAP = 10

export function recentWorkspaceIdentity(absolutePath: string): string {
  return `local:${absolutePath}`
}

export function buildRecentEntry(
  workspace: Pick<RecentWorkspaceEntry, 'absolutePath' | 'displayName'>,
  lastOpenedAt: string,
): RecentWorkspaceEntry {
  return {
    absolutePath: workspace.absolutePath,
    displayName: workspace.displayName,
    identity: recentWorkspaceIdentity(workspace.absolutePath),
    lastOpenedAt,
  }
}

/** Dedupe by identity, prepend the most-recent entry, cap the list. */
export function mergeRecent(
  list: RecentWorkspaceEntry[],
  entry: RecentWorkspaceEntry,
  cap = RECENT_CAP,
): RecentWorkspaceEntry[] {
  return [entry, ...list.filter((w) => w.identity !== entry.identity)].slice(0, cap)
}

export interface RecentWorkspacesLoad {
  entries: RecentWorkspaceEntry[]
  error: string | null
}

export interface RecentLoadDeps {
  list: () => Promise<RecentWorkspaceEntry[]>
  exists: (absolutePath: string) => Promise<boolean>
  remove: (identity: string) => Promise<void>
}

const defaultLoadDeps: RecentLoadDeps = {
  list: listRecentWorkspaces,
  exists: workspacePathExists,
  remove: removeRecentWorkspaceNative,
}

/** Fire a best-effort native MRU write, logging (never swallowing) any failure. */
function logRecentWriteFailure(action: string, promise: Promise<unknown>): void {
  promise.catch((error: unknown) => {
    console.warn('phase=recent-skills action=%s reason=%s', action, errorMessage(error))
  })
}

/**
 * Read the Recent MRU from the Rust native-fs store (`recent_workspaces.json`),
 * which is now the SINGLE source of truth (option B) — there is no second
 * localStorage copy to diverge from. Entries whose folder is gone from disk are
 * dropped from the rendered list AND pruned out of the same store, so a dead
 * card never lingers. Outside the desktop runtime the native list is empty and
 * the existence check degrades to "keep", so a web session simply shows no
 * Recent rather than mutating anything.
 *
 * A read failure surfaces a non-null `error` (logged at WARN, never silently
 * swallowed) while degrading `entries` to []. A per-entry existence-check
 * failure is treated as "keep" so a flaky check never wrongly hides a live
 * workspace.
 */
export async function loadRecentWorkspaces(
  deps: RecentLoadDeps = defaultLoadDeps,
): Promise<RecentWorkspacesLoad> {
  try {
    const entries = (await deps.list()).slice(0, RECENT_CAP)
    const flags = await Promise.all(
      entries.map((entry) => deps.exists(entry.absolutePath).catch(() => true)),
    )
    const present = entries.filter((_, index) => flags[index])
    const missing = entries.filter((_, index) => !flags[index])
    for (const dead of missing) {
      logRecentWriteFailure('prune', deps.remove(dead.identity))
    }
    return { entries: present, error: null }
  } catch (error) {
    const reason = errorMessage(error)
    console.warn('phase=recent-skills action=read-failed reason=%s', reason)
    return { entries: [], error: reason }
  }
}

export function useRecentSkills() {
  const [recentWorkspaces, setRecentWorkspaces] = useState<RecentWorkspaceEntry[]>([])
  // N1 atom #9: local error fallback. Holds the MRU read / path-validation
  // failure reason so Home renders a local red box (over the still-usable
  // New/Open entries) instead of silently swallowing the failure.
  const [recentError, setRecentError] = useState<string | null>(null)
  // Cold-start window: true for the first paint before the native MRU read
  // resolves. Home shows a Recent skeleton while this is true so the cold-start
  // moment is a placeholder, not a blank flash (D6).
  const [isHydrating, setIsHydrating] = useState(true)

  useEffect(() => {
    let cancelled = false
    loadRecentWorkspaces()
      .then((result) => {
        if (cancelled) return
        setRecentWorkspaces(result.entries)
        setRecentError(result.error)
      })
      .finally(() => {
        if (!cancelled) setIsHydrating(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const rememberWorkspace = useCallback(
    (workspace: Pick<RecentWorkspaceEntry, 'absolutePath' | 'displayName'>) => {
      const entry = buildRecentEntry(workspace, new Date().toISOString())
      // Optimistic local projection (snappy, survives the immediate navigate-away);
      // the Rust store is the persistent single source of truth and is re-read on
      // the next Home mount.
      setRecentWorkspaces((prev) => mergeRecent(prev, entry))
      logRecentWriteFailure(
        'remember',
        addRecentWorkspace(entry.absolutePath, entry.displayName, entry.identity, entry.lastOpenedAt),
      )
      return entry
    },
    [],
  )

  const removeWorkspace = useCallback((identity: string) => {
    setRecentWorkspaces((prev) => prev.filter((w) => w.identity !== identity))
    logRecentWriteFailure('remove', removeRecentWorkspaceNative(identity))
  }, [])

  return {
    recentWorkspaces,
    rememberWorkspace,
    removeWorkspace,
    isHydrating,
    recentError,
  }
}
