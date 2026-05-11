import { toast } from 'sonner'
import { isTauriRuntime } from '../config/runtime'

type TauriCommand = 'open_in_cursor' | 'open_in_terminal' | 'open_in_codex'

async function invokeShell(command: TauriCommand, path: string) {
  const targetPath = path.trim()
  if (!targetPath) {
    toast.error('No skill path available')
    return
  }

  if (!isTauriRuntime()) {
    toast.info('桌面端 only')
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

export async function selectSkillDirectory(): Promise<string | null> {
  if (!isTauriRuntime()) {
    toast.info('桌面端 only')
    return null
  }

  try {
    const moduleName = '@tauri-apps/plugin-dialog'
    const dialog = await import(/* @vite-ignore */ moduleName) as { open?: (options: { directory: boolean, multiple: boolean }) => Promise<string | string[] | null> }
    const selected = await dialog.open?.({ directory: true, multiple: false })
    return typeof selected === 'string' ? selected : null
  } catch {
    toast.error('Failed to open directory picker')
    return null
  }
}
