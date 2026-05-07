export function isTauriEnv(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
}

export async function verifyTauriWindowIpc(): Promise<boolean> {
  if (!isTauriEnv()) {
    return false
  }

  const { getCurrentWindow } = await import('@tauri-apps/api/window')
  await getCurrentWindow().setTitle('Skill Studio - Tauri Mode')
  return true
}
