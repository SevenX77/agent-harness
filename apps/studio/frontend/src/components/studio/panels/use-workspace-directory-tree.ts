import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { SkillDetail } from "@/api/types"
import { isTauriRuntime } from "@/config/runtime"
import { listWorkspaceDir, type WorkspaceDirEntry } from "@/lib/tauri"
import type { FileMeta } from "../file-types"
import { fileFromDetail, languageForPath } from "./panel-files"

export interface AssetTreeEntry {
  name: string
  path: string
  kind: "file" | "dir"
  file?: FileMeta
}

export type DirectoryTreeStatus = "idle" | "loading" | "ready" | "error"

export interface DirectoryTreeState {
  status: DirectoryTreeStatus
  entries: AssetTreeEntry[]
  message?: string
}

export interface WorkspaceDirectoryTree {
  isNative: boolean
  root: DirectoryTreeState
  getDirectory: (path: string) => DirectoryTreeState
  ensureDirectory: (path: string) => void
  reloadDirectory: (path: string) => void
}

interface UseWorkspaceDirectoryTreeOptions {
  workspaceRoot?: string | null
  skillId?: string | null
  titlePrefix?: string | null
  saveEnabled?: boolean
  enabled?: boolean
  skillDetail?: SkillDetail
}

type DirectorySnapshots = Record<string, DirectoryTreeState>

const EMPTY_DIRECTORY: DirectoryTreeState = { status: "idle", entries: [] }

function createFileMeta({
  path,
  content = "",
  skillId,
  workspaceRoot,
  titlePrefix,
  saveEnabled = true,
}: {
  path: string
  content?: string
  skillId?: string | null
  workspaceRoot?: string | null
  titlePrefix?: string | null
  saveEnabled?: boolean
}): FileMeta {
  return {
    path,
    language: languageForPath(path),
    content,
    skillId,
    workspaceRoot,
    title: titlePrefix ? `${titlePrefix} / ${path}` : undefined,
    saveEnabled,
  }
}

function normalizeDirectoryPath(path: string): string {
  const normalized = path.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "")
  return normalized === "." ? "" : normalized
}

function joinRelativePath(parent: string, name: string): string {
  const normalizedParent = normalizeDirectoryPath(parent)
  return normalizedParent ? `${normalizedParent}/${name}` : name
}

function sortEntries(entries: AssetTreeEntry[]): AssetTreeEntry[] {
  return [...entries].sort((left, right) => {
    if (left.kind !== right.kind) return left.kind === "dir" ? -1 : 1
    return left.name.localeCompare(right.name)
  })
}

function sortNativeEntries(entries: WorkspaceDirEntry[]): WorkspaceDirEntry[] {
  return [...entries].sort((left, right) => {
    if (left.kind !== right.kind) return left.kind === "dir" ? -1 : 1
    return left.name.localeCompare(right.name)
  })
}

function createReadySnapshot(entries: AssetTreeEntry[]): DirectoryTreeState {
  return { status: "ready", entries: sortEntries(entries) }
}

function fallbackSnapshotsFromSkillDetail(
  skillDetail: SkillDetail | undefined,
  options: {
    skillId?: string | null
    workspaceRoot?: string | null
  },
): DirectorySnapshots {
  const entryMaps = new Map<string, Map<string, AssetTreeEntry>>()
  const ensureEntryMap = (directoryPath: string) => {
    const normalized = normalizeDirectoryPath(directoryPath)
    let entries = entryMaps.get(normalized)
    if (!entries) {
      entries = new Map()
      entryMaps.set(normalized, entries)
    }
    return entries
  }

  ensureEntryMap("")

  for (const path of Object.keys(skillDetail?.files ?? {}).sort((a, b) => a.localeCompare(b))) {
    const parts = path.split("/").filter(Boolean)
    if (parts.length === 0) continue

    parts.forEach((part, index) => {
      const parentPath = parts.slice(0, index).join("/")
      const currentPath = parts.slice(0, index + 1).join("/")
      const isFile = index === parts.length - 1
      const parentEntries = ensureEntryMap(parentPath)
      let entry = parentEntries.get(part)

      if (!entry) {
        entry = {
          name: part,
          path: currentPath,
          kind: isFile ? "file" : "dir",
        }
        parentEntries.set(part, entry)
      }

      if (isFile) {
        entry.kind = "file"
        entry.file = {
          ...fileFromDetail(skillDetail, path),
          skillId: options.skillId,
          workspaceRoot: options.workspaceRoot,
        }
      } else {
        entry.kind = "dir"
        ensureEntryMap(currentPath)
      }
    })
  }

  const snapshots: DirectorySnapshots = {}
  for (const [directoryPath, entries] of entryMaps.entries()) {
    snapshots[directoryPath] = createReadySnapshot([...entries.values()])
  }
  return snapshots
}

function fallbackKey(skillDetail: SkillDetail | undefined): string {
  return Object.keys(skillDetail?.files ?? {}).sort((a, b) => a.localeCompare(b)).join("\u0001")
}

async function readNativeDirectory({
  workspaceRoot,
  relativeDir,
  skillId,
  titlePrefix,
  saveEnabled,
}: {
  workspaceRoot: string
  relativeDir: string
  skillId?: string | null
  titlePrefix?: string | null
  saveEnabled: boolean
}): Promise<AssetTreeEntry[]> {
  const directoryPath = normalizeDirectoryPath(relativeDir)
  const entries = sortNativeEntries(await listWorkspaceDir(workspaceRoot, directoryPath || "."))
  return entries.map((entry) => {
    const path = joinRelativePath(directoryPath, entry.name)
    const treeEntry: AssetTreeEntry = {
      name: entry.name,
      path,
      kind: entry.kind,
    }
    if (entry.kind === "file") {
      treeEntry.file = createFileMeta({
        path,
        skillId,
        workspaceRoot,
        titlePrefix,
        saveEnabled,
      })
    }
    return treeEntry
  })
}

export function useWorkspaceDirectoryTree({
  workspaceRoot,
  skillId,
  titlePrefix,
  saveEnabled = true,
  enabled = true,
  skillDetail,
}: UseWorkspaceDirectoryTreeOptions): WorkspaceDirectoryTree {
  const native = isTauriRuntime()
  const resolvedRoot = workspaceRoot?.trim() || null
  const fallbackRefreshKey = fallbackKey(skillDetail)
  const fallbackSnapshots = useMemo(
    () => fallbackSnapshotsFromSkillDetail(skillDetail, { skillId, workspaceRoot: resolvedRoot }),
    [resolvedRoot, skillDetail, skillId],
  )
  const [snapshots, setSnapshots] = useState<DirectorySnapshots>(() => {
    if (!enabled) {
      return { "": { status: "idle", entries: [] } }
    }
    if (native) {
      return { "": { status: resolvedRoot ? "loading" : "idle", entries: [] } }
    }
    return fallbackSnapshots
  })
  const snapshotsRef = useRef(snapshots)
  const requestTokenRef = useRef<Record<string, number>>({})

  useEffect(() => {
    snapshotsRef.current = snapshots
  }, [snapshots])

  const loadDirectory = useCallback((rawPath: string, force = false) => {
    if (!enabled || !resolvedRoot || !native) return

    const path = normalizeDirectoryPath(rawPath)
    const current = snapshotsRef.current[path]
    if (!force && (current?.status === "loading" || current?.status === "ready")) {
      return
    }

    const token = (requestTokenRef.current[path] ?? 0) + 1
    requestTokenRef.current[path] = token

    setSnapshots((existing) => ({
      ...existing,
      [path]: {
        status: "loading",
        entries: existing[path]?.entries ?? [],
      },
    }))

    void readNativeDirectory({
      workspaceRoot: resolvedRoot,
      relativeDir: path,
      skillId,
      titlePrefix,
      saveEnabled,
    })
      .then((entries) => {
        if (requestTokenRef.current[path] !== token) return
        setSnapshots((existing) => ({
          ...existing,
          [path]: createReadySnapshot(entries),
        }))
        // Eager (non-lazy) load: pull every source subdirectory up front so the
        // whole tree is loaded without expanding folder by folder. Runtime/hidden
        // dirs (.workspace runtime state, .git, ...) are skipped — they can be huge
        // and stay on-demand via ensureDirectory when actually expanded.
        for (const entry of entries) {
          if (entry.kind === "dir" && !entry.name.startsWith(".")) {
            loadDirectoryRef.current(entry.path, false)
          }
        }
      })
      .catch((error) => {
        if (requestTokenRef.current[path] !== token) return
        setSnapshots((existing) => ({
          ...existing,
          [path]: {
            status: "error",
            entries: existing[path]?.entries ?? [],
            message: error instanceof Error ? error.message : String(error || "Could not read folder"),
          },
        }))
      })
  }, [enabled, native, resolvedRoot, saveEnabled, skillId, titlePrefix])
  // Stable handle so loadDirectory's success cascade can recurse without making
  // loadDirectory depend on itself.
  const loadDirectoryRef = useRef(loadDirectory)
  loadDirectoryRef.current = loadDirectory

  useEffect(() => {
    if (!enabled) {
      requestTokenRef.current = {}
      setSnapshots({ "": { status: "idle", entries: [] } })
      return
    }

    if (!native) return
    if (!resolvedRoot) {
      requestTokenRef.current = {}
      setSnapshots({ "": { status: "idle", entries: [] } })
      return
    }

    requestTokenRef.current = {}
    setSnapshots({ "": { status: "loading", entries: snapshotsRef.current[""]?.entries ?? [] } })
    loadDirectory("", true)
  }, [enabled, loadDirectory, native, resolvedRoot])

  useEffect(() => {
    if (!enabled || (resolvedRoot && native)) return

    requestTokenRef.current = {}
    setSnapshots(fallbackSnapshots)
  }, [enabled, fallbackSnapshots, native, resolvedRoot])

  useEffect(() => {
    if (!enabled || !resolvedRoot || !native) return

    const loadedDirectories = Object.entries(snapshotsRef.current)
      .filter(([, snapshot]) => snapshot.status === "ready" || snapshot.status === "error")
      .map(([path]) => path)

    if (loadedDirectories.length === 0) return
    loadedDirectories.forEach((path) => loadDirectory(path, true))
  }, [enabled, fallbackRefreshKey, loadDirectory, native, resolvedRoot])

  // Re-list every loaded directory when the window regains focus (or the document
  // becomes visible). The backend file watcher only covers the app's config skills
  // dirs, so it never sees external changes to a workspace opened from an arbitrary
  // folder. Refreshing on focus catches those — a file deleted/added in the OS file
  // manager shows up the moment the user switches back to Studio, like a native
  // explorer. Native runtime only; the browser fallback has no live disk to re-read.
  useEffect(() => {
    if (!enabled || !resolvedRoot || !native) return
    if (typeof window === "undefined") return

    const reloadLoaded = () => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return
      for (const [path, snapshot] of Object.entries(snapshotsRef.current)) {
        if (snapshot.status === "ready" || snapshot.status === "error") {
          loadDirectory(path, true)
        }
      }
    }

    window.addEventListener("focus", reloadLoaded)
    document.addEventListener("visibilitychange", reloadLoaded)
    return () => {
      window.removeEventListener("focus", reloadLoaded)
      document.removeEventListener("visibilitychange", reloadLoaded)
    }
  }, [enabled, loadDirectory, native, resolvedRoot])

  const getDirectory = useCallback((path: string) => {
    return snapshots[normalizeDirectoryPath(path)] ?? EMPTY_DIRECTORY
  }, [snapshots])

  const ensureDirectory = useCallback((path: string) => {
    loadDirectory(path, false)
  }, [loadDirectory])

  const reloadDirectory = useCallback((path: string) => {
    loadDirectory(path, true)
  }, [loadDirectory])

  return useMemo(() => ({
    isNative: native,
    root: snapshots[""] ?? EMPTY_DIRECTORY,
    getDirectory,
    ensureDirectory,
    reloadDirectory,
  }), [getDirectory, ensureDirectory, native, reloadDirectory, snapshots])
}
