import { afterEach, describe, expect, it, vi } from 'vitest'
import { invoke } from '@tauri-apps/api/core'
import { toast } from 'sonner'
import { selectSkillDirectory } from './tauri'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    info: vi.fn(),
  },
}))

const mockInvoke = vi.mocked(invoke)

describe('selectSkillDirectory', () => {
  afterEach(() => {
    vi.clearAllMocks()
    vi.unstubAllGlobals()
  })

  it('opens the native directory picker in Tauri', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    mockInvoke.mockResolvedValue('/tmp/imported-skill')

    await expect(selectSkillDirectory()).resolves.toBe('/tmp/imported-skill')

    expect(mockInvoke).toHaveBeenCalledWith('select_directory', { defaultPath: null })
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('passes the default folder to the native picker', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    mockInvoke.mockResolvedValue('/tmp/imported-skill')

    await expect(selectSkillDirectory('/tmp/default-skills')).resolves.toBe('/tmp/imported-skill')

    expect(mockInvoke).toHaveBeenCalledWith('select_directory', {
      defaultPath: '/tmp/default-skills',
    })
  })

  it('shows the picker failure reason', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    mockInvoke.mockRejectedValue(new Error('dialog permission denied'))

    await expect(selectSkillDirectory()).resolves.toBeNull()

    expect(toast.error).toHaveBeenCalledWith('Failed to open directory picker', {
      description: 'dialog permission denied',
    })
  })
})
