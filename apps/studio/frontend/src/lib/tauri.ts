import { toast } from 'sonner'
import { isTauriRuntime } from '../config/runtime'

export interface RecentWorkspaceEntry {
  absolutePath: string
  displayName: string
  identity: string
  lastOpenedAt: string
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

  toast.info('Desktop-only feature', { description: targetPath })
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
