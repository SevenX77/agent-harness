import { toast } from 'sonner'
import { isTauriRuntime } from '../config/runtime'

export interface RecentWorkspaceEntry {
  absolutePath: string
  displayName: string
  identity: string
  lastOpenedAt: string
}

type TauriCommand = 'open_in_cursor' | 'open_in_terminal' | 'open_in_codex' | 'reveal_in_file_manager'

async function invokeShell(command: TauriCommand, path: string) {
  const targetPath = path.trim()
  if (!targetPath) {
    toast.error('No skill path available')
    return
  }

  if (!isTauriRuntime()) {
    toast.info('Desktop only')
    return
  }

  try {
    const { invoke } = await import('@tauri-apps/api/core')
    await invoke(command, { path: targetPath })
  } catch {
    toast.error('Failed to open desktop tool')
  }
}

export function openInCursor(path: string) {
  return invokeShell('open_in_cursor', path)
}

export function openInTerminal(path: string) {
  return invokeShell('open_in_terminal', path)
}

export function openInCodex(path: string) {
  return invokeShell('open_in_codex', path)
}

export async function revealInFileManager(path: string) {
  const targetPath = path.trim()
  if (!targetPath) {
    toast.error('No skill path available')
    return
  }

  if (isTauriRuntime()) {
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

export async function selectSkillDirectory(defaultDirectory?: string | null): Promise<string | null> {
  if (!isTauriRuntime()) {
    toast.info('Desktop only')
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

export async function writeWorkspaceFile(
  workspaceRoot: string,
  path: string,
  content: string,
  expectedHash: string | null = null,
): Promise<{ path: string; hash: string }> {
  if (!isTauriRuntime()) {
    throw new Error('Desktop only')
  }
  const { invoke } = await import('@tauri-apps/api/core')
  return await invoke<{ path: string; hash: string }>('write_workspace_file', {
    workspaceRoot,
    path,
    content,
    expectedHash,
  })
}

export async function addRecentWorkspace(
  absolutePath: string,
  displayName: string,
  identity: string,
  lastOpenedAt: string,
): Promise<void> {
  if (!isTauriRuntime()) return
  const { invoke } = await import('@tauri-apps/api/core')
  await invoke('add_recent_workspace', {
    absolutePath,
    displayName,
    identity,
    lastOpenedAt,
  })
}

export async function listRecentWorkspaces(): Promise<RecentWorkspaceEntry[]> {
  if (!isTauriRuntime()) return []
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
  if (!isTauriRuntime()) return
  const { invoke } = await import('@tauri-apps/api/core')
  await invoke('remove_recent_workspace', { identity })
}

export async function ensureWorkspaceSupportDirs(workspaceRoot: string): Promise<void> {
  if (!isTauriRuntime()) return
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
  if (!isTauriRuntime()) {
    throw new Error('Desktop only')
  }
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
  if (!isTauriRuntime()) return []
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
  if (!isTauriRuntime()) {
    throw new Error('Desktop only')
  }
  const { invoke } = await import('@tauri-apps/api/core')
  return await invoke<CheckpointResult>('checkpoint_workspace_file', { workspaceRoot, path })
}

/** Reject: restore a file to its checkpointed pre-edit state via the sole writer. */
export async function restoreWorkspaceFile(
  workspaceRoot: string,
  path: string,
): Promise<RestoreResult> {
  if (!isTauriRuntime()) {
    throw new Error('Desktop only')
  }
  const { invoke } = await import('@tauri-apps/api/core')
  return await invoke<RestoreResult>('restore_workspace_file', { workspaceRoot, path })
}

/** Accept: discard the checkpoint, keeping the applied edit. */
export async function clearWorkspaceCheckpoint(
  workspaceRoot: string,
  path: string,
): Promise<void> {
  if (!isTauriRuntime()) return
  const { invoke } = await import('@tauri-apps/api/core')
  await invoke('clear_workspace_checkpoint', { workspaceRoot, path })
}
