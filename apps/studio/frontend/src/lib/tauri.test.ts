import { afterEach, describe, expect, it, vi } from 'vitest'
import { invoke } from '@tauri-apps/api/core'
import { toast } from 'sonner'
import * as tauriBridge from './tauri'
import { revealInFileManager, selectSkillDirectory } from './tauri'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    info: vi.fn(),
    success: vi.fn(),
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

describe('Tauri native-fs bridge contract', () => {
  afterEach(() => {
    vi.clearAllMocks()
    vi.unstubAllGlobals()
  })

  it('does not expose retired external IDE or terminal helpers', () => {
    expect(tauriBridge).not.toHaveProperty('openInCursor')
    expect(tauriBridge).not.toHaveProperty('openInTerminal')
    expect(tauriBridge).not.toHaveProperty('openInCodex')
  })

  it('does not fake a successful reveal action in browser fallback', async () => {
    const writeText = vi.fn()
    vi.stubGlobal('window', {})
    vi.stubGlobal('navigator', {
      clipboard: { writeText },
    })

    await revealInFileManager('/workspace/plain-folder')

    expect(writeText).not.toHaveBeenCalled()
    expect(toast.info).toHaveBeenCalledWith('Desktop-only feature', {
      description: '/workspace/plain-folder',
    })
    expect(toast.success).not.toHaveBeenCalled()
  })
})
