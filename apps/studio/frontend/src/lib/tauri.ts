import { toast } from 'sonner'
import { isTauriRuntime } from '../config/runtime'

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

export async function selectSkillDirectory(): Promise<string | null> {
  if (!isTauriRuntime()) {
    toast.info('Desktop only')
    return null
  }

  try {
    const { invoke } = await import('@tauri-apps/api/core')
    const selected = await invoke<string | null>('select_directory')
    return typeof selected === 'string' ? selected : null
  } catch (error) {
    const description = error instanceof Error ? error.message : String(error)
    toast.error('Failed to open directory picker', { description })
    return null
  }
}
