import { toast } from 'sonner'
import { getRuntimeStatus, isTauriRuntime } from '../config/runtime'
import type { ReleaseArtifactRef } from '../api/types'

export interface RecentWorkspaceEntry {
  absolutePath: string
  displayName: string
  identity: string
  lastOpenedAt: string
}

function desktopRuntimeUnavailableError(): Error {
  const status = getRuntimeStatus()
  return new Error(
    status.message ? `Desktop runtime unavailable: ${status.message}` : 'Desktop runtime unavailable',
  )
}

function toastDesktopRuntimeUnavailable(): void {
  const status = getRuntimeStatus()
  if (status.message) {
    toast.error('Desktop runtime unavailable', { description: status.message })
    return
  }
  toast.error('Desktop runtime unavailable')
}

function nativeHelpersAreAvailable(): boolean {
  return getRuntimeStatus().nativeHelpersAvailable
}

function assertNativeHelpersAvailable(): void {
  if (!isTauriRuntime()) {
    throw new Error('Desktop only')
  }
  if (!nativeHelpersAreAvailable()) {
    throw desktopRuntimeUnavailableError()
  }
}

export async function revealInFileManager(path: string) {
  const targetPath = path.trim()
  if (!targetPath) {
    toast.error('No skill path available')
    return
  }

  if (isTauriRuntime()) {
    if (!nativeHelpersAreAvailable()) {
      toastDesktopRuntimeUnavailable()
      return
    }
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      await invoke('reveal_in_file_manager', { path: targetPath })
      return
    } catch {
      toast.error('Failed to reveal in file manager')
      return
    }
  }

  try {
    await navigator.clipboard.writeText(targetPath)
    toast.success('Path copied to clipboard', { description: targetPath })
  } catch {
    toast.info('Desktop-only feature', { description: targetPath })
  }
}

export async function openLocalPath(path: string): Promise<boolean> {
  const targetPath = path.trim()
  if (!targetPath) {
    toast.error('No path available')
    return false
  }

  if (isTauriRuntime()) {
    if (!nativeHelpersAreAvailable()) {
      toastDesktopRuntimeUnavailable()
      return false
    }
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      await invoke('open_path', { path: targetPath })
      return true
    } catch (error) {
      const description = error instanceof Error ? error.message : String(error)
      toast.error('Failed to open path', { description })
      return false
    }
  }

  try {
    await navigator.clipboard.writeText(targetPath)
    toast.success('Path copied to clipboard', { description: targetPath })
  } catch {
    toast.info('Desktop-only feature', { description: targetPath })
  }
  return false
}

export async function openClaudeCode(workspaceRoot: string | null | undefined): Promise<boolean> {
  const targetPath = workspaceRoot?.trim() ?? ''
  if (!targetPath) {
    toast.error('No workspace path available')
    return false
  }

  if (!isTauriRuntime()) {
    toast.info('Desktop-only feature', { description: targetPath })
    return false
  }
  if (!nativeHelpersAreAvailable()) {
    toastDesktopRuntimeUnavailable()
    return false
  }

  try {
    const { invoke } = await import('@tauri-apps/api/core')
    await invoke('open_claude_code', { workspaceRoot: targetPath })
    toast.success('Opening Claude Code')
    return true
  } catch (error) {
    const description = error instanceof Error ? error.message : String(error)
    toast.error('Failed to open Claude Code', { description })
    return false
  }
}

export async function selectSkillDirectory(defaultDirectory?: string | null): Promise<string | null> {
  if (!isTauriRuntime()) {
    toast.info('Desktop only')
    return null
  }
  if (!nativeHelpersAreAvailable()) {
    toastDesktopRuntimeUnavailable()
    return null
  }

  try {
    const { invoke } = await import('@tauri-apps/api/core')
    const selected = await invoke<string | null>('select_directory', {
      defaultPath: defaultDirectory?.trim() || null,
    })
    return typeof selected === 'string' ? selected : null
  } catch (error) {
    const description = error instanceof Error ? error.message : String(error)
    toast.error('Failed to open directory picker', { description })
    return null
  }
}

export interface SkillWorkspaceResult {
  root: string
  skillId: string
}

/**
 * Create a new skill on disk via the Rust native-fs sole writer (D12): builds
 * the skill dir + scaffold, runs git init, and writes the skill_index entry so
 * the read-detail sidecar GET resolves id->dir. Replaces the Python POST /skills
 * create path. `parentDirectory` blank -> Rust defaults to the config Skills dir.
 */
export async function createSkillWorkspace(
  parentDirectory: string,
  skillId: string,
): Promise<SkillWorkspaceResult> {
  assertNativeHelpersAvailable()
  const { invoke } = await import('@tauri-apps/api/core')
  const result = await invoke<{ root: string; skill_id: string }>('create_skill_workspace', {
    parentDirectory,
    skillId,
  })
  return { root: result.root, skillId: result.skill_id }
}

/**
 * Register an opened folder as a workspace via the Rust native-fs writer (D2:
 * OS checks only, no manifest validation): derives the skill id from the path
 * and writes the skill_index entry. Replaces the Python POST /skills import path.
 */
export async function openSkillWorkspace(directory: string): Promise<SkillWorkspaceResult> {
  assertNativeHelpersAvailable()
  const { invoke } = await import('@tauri-apps/api/core')
  const result = await invoke<{ root: string; skill_id: string }>('open_skill_workspace', {
    directory,
  })
  return { root: result.root, skillId: result.skill_id }
}

/**
 * Read-only existence check used by stale-MRU pruning. Degrades like the other
 * read/list native helpers: outside the desktop runtime it returns `true` so a
 * web session never prunes its localStorage MRU on a missing native channel.
 */
export async function workspacePathExists(path: string): Promise<boolean> {
  if (!isTauriRuntime() || !nativeHelpersAreAvailable()) return true
  const { invoke } = await import('@tauri-apps/api/core')
  return await invoke<boolean>('workspace_path_exists', { path })
}

export async function writeWorkspaceFile(
  workspaceRoot: string,
  path: string,
  content: string,
  expectedHash: string | null = null,
  options: { createIfAbsent?: boolean } = {},
): Promise<{ path: string; hash: string }> {
  assertNativeHelpersAvailable()
  const { invoke } = await import('@tauri-apps/api/core')
  const payload: {
    workspaceRoot: string
    relativePath: string
    content: string
    expectedHash: string | null
    createIfAbsent?: boolean
  } = {
    workspaceRoot,
    relativePath: path,
    content,
    expectedHash,
  }
  if (options.createIfAbsent) {
    payload.createIfAbsent = true
  }
  return await invoke<{ path: string; hash: string }>('write_workspace_file', payload)
}

export interface WritePublishPackageRequest {
  workspaceRoot: string
  relativePath: string
  releaseVersion: string
  contentHash: string
  manifestRef: string
  artifactRef: ReleaseArtifactRef
}

export interface WritePublishPackageResult {
  path: string
  nativePath: string
  hash: string
  bytesWritten: number
}

export async function writePublishPackage(
  request: WritePublishPackageRequest,
): Promise<WritePublishPackageResult> {
  assertNativeHelpersAvailable()
  const { invoke } = await import('@tauri-apps/api/core')
  return await invoke<WritePublishPackageResult>('publish_package_writer', {
    workspaceRoot: request.workspaceRoot,
    relativePath: request.relativePath,
    releaseVersion: request.releaseVersion,
    contentHash: request.contentHash,
    manifestRef: request.manifestRef,
    artifactRef: request.artifactRef,
  })
}

export async function deleteWorkspacePath(
  workspaceRoot: string,
  path: string,
): Promise<void> {
  assertNativeHelpersAvailable()
  const { invoke } = await import('@tauri-apps/api/core')
  await invoke('delete_workspace_path', {
    workspaceRoot,
    path,
  })
}

export async function moveWorkspacePath(
  workspaceRoot: string,
  from: string,
  to: string,
): Promise<void> {
  assertNativeHelpersAvailable()
  const { invoke } = await import('@tauri-apps/api/core')
  await invoke('move_workspace_path', {
    workspaceRoot,
    from,
    to,
  })
}

export async function addRecentWorkspace(
  absolutePath: string,
  displayName: string,
  identity: string,
  lastOpenedAt: string,
): Promise<void> {
  if (!isTauriRuntime() || !nativeHelpersAreAvailable()) return
  const { invoke } = await import('@tauri-apps/api/core')
  await invoke('add_recent_workspace', {
    absolutePath,
    displayName,
    identity,
    lastOpenedAt,
  })
}

export async function listRecentWorkspaces(): Promise<RecentWorkspaceEntry[]> {
  if (!isTauriRuntime() || !nativeHelpersAreAvailable()) return []
  const { invoke } = await import('@tauri-apps/api/core')
  const raw = await invoke<Array<{
    absolute_path: string
    display_name: string
    identity: string
    last_opened_at: string
  }>>('list_recent_workspaces')
  return raw.map((item) => ({
    absolutePath: item.absolute_path,
    displayName: item.display_name,
    identity: item.identity,
    lastOpenedAt: item.last_opened_at,
  }))
}

export async function removeRecentWorkspace(identity: string): Promise<void> {
  if (!isTauriRuntime() || !nativeHelpersAreAvailable()) return
  const { invoke } = await import('@tauri-apps/api/core')
  await invoke('remove_recent_workspace', { identity })
}

export async function ensureWorkspaceSupportDirs(workspaceRoot: string): Promise<void> {
  if (!isTauriRuntime() || !nativeHelpersAreAvailable()) return
  const { invoke } = await import('@tauri-apps/api/core')
  await invoke('ensure_workspace_support_dirs', { workspaceRoot })
}

export interface ReadWorkspaceFileResult {
  path: string
  content: string
  hash: string
}

export async function readWorkspaceFile(
  workspaceRoot: string,
  path: string,
): Promise<ReadWorkspaceFileResult> {
  assertNativeHelpersAvailable()
  const { invoke } = await import('@tauri-apps/api/core')
  return await invoke<ReadWorkspaceFileResult>('read_workspace_file', {
    workspaceRoot,
    path,
  })
}

export interface WorkspaceDirEntry {
  name: string
  kind: 'file' | 'dir'
}

export async function listWorkspaceDir(
  workspaceRoot: string,
  relativeDir: string,
): Promise<WorkspaceDirEntry[]> {
  if (!isTauriRuntime() || !nativeHelpersAreAvailable()) return []
  const { invoke } = await import('@tauri-apps/api/core')
  return await invoke<WorkspaceDirEntry[]>('list_workspace_dir', {
    workspaceRoot,
    relativeDir,
  })
}

// ── Safe-write checkpoints (copilot F5) ──────────────────────────────────────

export interface CheckpointResult {
  path: string
  existed: boolean
  created: boolean
}

export interface RestoreResult {
  path: string
  existed: boolean
  content: string
}

/** Capture a file's pre-edit bytes so a Reject can restore them (copilot F5). */
export async function checkpointWorkspaceFile(
  workspaceRoot: string,
  path: string,
): Promise<CheckpointResult> {
  assertNativeHelpersAvailable()
  const { invoke } = await import('@tauri-apps/api/core')
  return await invoke<CheckpointResult>('checkpoint_workspace_file', { workspaceRoot, path })
}

/**
 * Seed a checkpoint from explicit pre-edit state (copilot F5). The backend ships
 * before-bytes in the patch_proposed event; recording them here is race-free
 * (re-reading would capture the already-applied edit).
 */
export async function seedWorkspaceCheckpoint(
  workspaceRoot: string,
  path: string,
  content: string,
  existed: boolean,
): Promise<CheckpointResult> {
  assertNativeHelpersAvailable()
  const { invoke } = await import('@tauri-apps/api/core')
  return await invoke<CheckpointResult>('seed_workspace_checkpoint', {
    workspaceRoot,
    path,
    content,
    existed,
  })
}

/** Reject: restore a file to its checkpointed pre-edit state via the sole writer. */
export async function restoreWorkspaceFile(
  workspaceRoot: string,
  path: string,
): Promise<RestoreResult> {
  assertNativeHelpersAvailable()
  const { invoke } = await import('@tauri-apps/api/core')
  return await invoke<RestoreResult>('restore_workspace_file', { workspaceRoot, path })
}

/** Accept: discard the checkpoint, keeping the applied edit. */
export async function clearWorkspaceCheckpoint(
  workspaceRoot: string,
  path: string,
): Promise<void> {
  assertNativeHelpersAvailable()
  const { invoke } = await import('@tauri-apps/api/core')
  await invoke('clear_workspace_checkpoint', { workspaceRoot, path })
}
