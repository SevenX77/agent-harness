import { afterEach, describe, expect, it, vi } from 'vitest'
import { invoke } from '@tauri-apps/api/core'
import { toast } from 'sonner'
import { initializeRuntimeConfig } from '../config/runtime'
import * as tauriModule from './tauri'
import {
  attachCodeAssistant,
  checkpointWorkspaceFile,
  clearWorkspaceCheckpoint,
  closeCodeAssistant,
  createSkillWorkspace,
  deleteWorkspacePath,
  getCodeAssistantStatus,
  openClaudeCode,
  openCodexCli,
  openSkillWorkspace,
  readWorkspaceFile,
  restoreWorkspaceFile,
  revealInFileManager,
  seedWorkspaceCheckpoint,
  selectFile,
  selectSkillDirectory,
  workspacePathExists,
  writePublishPackage,
  writeWorkspaceFile,
} from './tauri'

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

async function resetRuntimeForTest() {
  await initializeRuntimeConfig({
    windowRef: {},
    fallbackBaseURL: 'http://localhost:8787/api',
  })
}

async function markRuntimeReady() {
  await initializeRuntimeConfig({
    windowRef: { __TAURI_INTERNALS__: {} },
    invoke: async <T,>() =>
      ({
        port: 49152,
        baseURL: 'http://127.0.0.1:49152/api',
        wsURL: 'ws://127.0.0.1:49152/ws',
        resourceDir: '/tmp/studio',
        configDir: '/tmp/studio-config',
        api_token: null,
      }) as T,
  })
}

async function markRuntimeDegraded() {
  await expect(
    initializeRuntimeConfig({
      windowRef: { __TAURI_INTERNALS__: {} },
      invoke: async () => {
        throw new Error('sidecar disabled')
      },
    }),
  ).rejects.toThrow('sidecar disabled')
}

afterEach(async () => {
  vi.unstubAllGlobals()
  await resetRuntimeForTest()
  vi.clearAllMocks()
})

describe('selectSkillDirectory', () => {
  it('opens the native directory picker in Tauri', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockResolvedValue('/tmp/imported-skill')

    await expect(selectSkillDirectory()).resolves.toBe('/tmp/imported-skill')

    expect(mockInvoke).toHaveBeenCalledWith('select_directory', { defaultPath: null })
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('passes the default folder to the native picker', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockResolvedValue('/tmp/imported-skill')

    await expect(selectSkillDirectory('/tmp/default-skills')).resolves.toBe('/tmp/imported-skill')

    expect(mockInvoke).toHaveBeenCalledWith('select_directory', {
      defaultPath: '/tmp/default-skills',
    })
  })

  it('shows the picker failure reason', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockRejectedValue(new Error('dialog permission denied'))

    await expect(selectSkillDirectory()).resolves.toBeNull()

    expect(toast.error).toHaveBeenCalledWith('Failed to open directory picker', {
      description: 'dialog permission denied',
    })
  })

  it('opens the native directory picker when only the sidecar is degraded', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeDegraded()
    mockInvoke.mockResolvedValue('/tmp/imported-skill')

    await expect(selectSkillDirectory()).resolves.toBe('/tmp/imported-skill')

    expect(mockInvoke).toHaveBeenCalledWith('select_directory', { defaultPath: null })
    expect(toast.error).not.toHaveBeenCalled()
  })
})

describe('selectFile', () => {
  it('opens the native file picker in Tauri with the default folder', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockResolvedValue('/tmp/workspace/.workspace/copilot/sessions/demo/session-1.json')

    await expect(selectFile('/tmp/workspace/.workspace/copilot/sessions/demo')).resolves.toBe(
      '/tmp/workspace/.workspace/copilot/sessions/demo/session-1.json',
    )

    expect(mockInvoke).toHaveBeenCalledWith('select_file', {
      defaultPath: '/tmp/workspace/.workspace/copilot/sessions/demo',
    })
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('returns null outside desktop runtime', async () => {
    vi.stubGlobal('window', { location: { origin: 'http://localhost:5173' } })
    await resetRuntimeForTest()

    await expect(selectFile('/tmp/default')).resolves.toBeNull()

    expect(mockInvoke).not.toHaveBeenCalled()
    expect(toast.info).toHaveBeenCalledWith('Desktop only')
  })

  it('shows the picker failure reason', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockRejectedValue(new Error('dialog permission denied'))

    await expect(selectFile('/tmp/default')).resolves.toBeNull()

    expect(toast.error).toHaveBeenCalledWith('Failed to open file picker', {
      description: 'dialog permission denied',
    })
  })
})

describe('desktop shell helpers', () => {
  it('invokes the reveal command when only the sidecar is degraded', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeDegraded()
    mockInvoke.mockResolvedValue(undefined)

    await expect(revealInFileManager('/tmp/workspace')).resolves.toBeUndefined()

    expect(mockInvoke).toHaveBeenCalledWith('reveal_in_file_manager', {
      path: '/tmp/workspace',
    })
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('opens Claude Code through the native ah launcher', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockResolvedValue(undefined)

    await expect(openClaudeCode('/tmp/workspace')).resolves.toBe(true)

    expect(mockInvoke).toHaveBeenCalledWith('open_claude_code', {
      workspaceRoot: '/tmp/workspace',
    })
  })

  it('does not invoke the Claude Code launcher outside desktop runtime', async () => {
    vi.stubGlobal('window', { location: { origin: 'http://localhost:5173' } })
    await resetRuntimeForTest()

    await expect(openClaudeCode('/tmp/workspace')).resolves.toBe(false)

    expect(mockInvoke).not.toHaveBeenCalled()
    expect(toast.info).toHaveBeenCalledWith('Desktop-only feature', {
      description: '/tmp/workspace',
    })
  })

  it('opens Codex CLI through the native ah launcher', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockResolvedValue(undefined)

    await expect(openCodexCli('/tmp/workspace')).resolves.toBe(true)

    expect(mockInvoke).toHaveBeenCalledWith('open_codex_cli', {
      workspaceRoot: '/tmp/workspace',
    })
  })

  it('does not invoke the Codex launcher outside desktop runtime', async () => {
    vi.stubGlobal('window', { location: { origin: 'http://localhost:5173' } })
    await resetRuntimeForTest()

    await expect(openCodexCli('/tmp/workspace')).resolves.toBe(false)

    expect(mockInvoke).not.toHaveBeenCalled()
    expect(toast.info).toHaveBeenCalledWith('Desktop-only feature', {
      description: '/tmp/workspace',
    })
  })

  it('reads code assistant ahd status through the native shell', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockResolvedValue({ claude: true, codex: false })

    await expect(getCodeAssistantStatus('/tmp/workspace')).resolves.toEqual({ claude: true, codex: false })

    expect(mockInvoke).toHaveBeenCalledWith('code_assistant_status', {
      workspaceRoot: '/tmp/workspace',
    })
  })

  it('treats code assistants as inactive outside desktop runtime', async () => {
    vi.stubGlobal('window', { location: { origin: 'http://localhost:5173' } })
    await resetRuntimeForTest()

    await expect(getCodeAssistantStatus('/tmp/workspace')).resolves.toEqual({ claude: false, codex: false })

    expect(mockInvoke).not.toHaveBeenCalled()
  })

  it('closes the selected code assistant through ah', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockResolvedValue(true)

    await expect(closeCodeAssistant('/tmp/workspace', 'codex')).resolves.toBe(true)

    expect(mockInvoke).toHaveBeenCalledWith('close_code_assistant', {
      workspaceRoot: '/tmp/workspace',
      assistant: 'codex',
    })
  })

  it('attaches the selected code assistant master pane through ah', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockResolvedValue(undefined)

    await expect(attachCodeAssistant('/tmp/workspace', 'claude')).resolves.toBe(true)

    expect(mockInvoke).toHaveBeenCalledWith('attach_code_assistant', {
      workspaceRoot: '/tmp/workspace',
      assistant: 'claude',
    })
  })
})

describe('writeWorkspaceFile', () => {
  it('passes workspaceRoot, relativePath, content, and expectedHash to the Tauri writer', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockResolvedValue({ path: 'GRAPH.md', hash: 'native-hash' })

    await expect(
      writeWorkspaceFile('/tmp/workspace', 'GRAPH.md', 'graph body', 'expected-hash'),
    ).resolves.toEqual({ path: 'GRAPH.md', hash: 'native-hash' })

    expect(mockInvoke).toHaveBeenCalledWith('write_workspace_file', {
      workspaceRoot: '/tmp/workspace',
      relativePath: 'GRAPH.md',
      content: 'graph body',
      expectedHash: 'expected-hash',
    })
    const [, payload] = mockInvoke.mock.calls[0] as [string, Record<string, unknown>]
    expect(payload).not.toHaveProperty('path')
    expect(payload).not.toHaveProperty('createIfAbsent')
  })

  it('passes createIfAbsent only when the caller requests no-clobber writes', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockResolvedValue({ path: '.workspace/import_files/case.json', hash: 'native-hash' })

    await expect(
      writeWorkspaceFile(
        '/tmp/workspace',
        '.workspace/import_files/case.json',
        '{\n  "x": 1\n}',
        null,
        { createIfAbsent: true },
      ),
    ).resolves.toEqual({ path: '.workspace/import_files/case.json', hash: 'native-hash' })

    expect(mockInvoke).toHaveBeenCalledWith('write_workspace_file', {
      workspaceRoot: '/tmp/workspace',
      relativePath: '.workspace/import_files/case.json',
      content: '{\n  "x": 1\n}',
      expectedHash: null,
      createIfAbsent: true,
    })
  })

  it('uses the native writer when only the sidecar is degraded', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeDegraded()
    mockInvoke.mockResolvedValue({ path: 'GRAPH.md', hash: 'native-hash' })

    await expect(writeWorkspaceFile('/tmp/workspace', 'GRAPH.md', 'graph body')).resolves.toEqual({
      path: 'GRAPH.md',
      hash: 'native-hash',
    })

    expect(mockInvoke).toHaveBeenCalledWith('write_workspace_file', {
      workspaceRoot: '/tmp/workspace',
      relativePath: 'GRAPH.md',
      content: 'graph body',
      expectedHash: null,
    })
  })
})

describe('writePublishPackage', () => {
  it('invokes the Tauri native publish package writer with release manifest identity', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockResolvedValue({
      path: '.workspace/releases/text-segmentation-1.0.0.package.json',
      nativePath: '/tmp/workspace/.workspace/releases/text-segmentation-1.0.0.package.json',
      hash: 'package-hash',
      bytesWritten: 512,
    })

    await expect(
      writePublishPackage({
        workspaceRoot: '/tmp/workspace',
        relativePath: '.workspace/releases/text-segmentation-1.0.0.package.json',
        releaseVersion: '1.0.0',
        contentHash: `sha256:${'a'.repeat(64)}`,
        manifestRef: 'product/releases/text-segmentation/1.0.0.json',
        artifactRef: {
          artifact_id: 'text-segmentation',
          store: 'product',
          content_hash: `sha256:${'a'.repeat(64)}`,
          manifest_ref: 'product/manifests/text-segmentation.json',
        },
      }),
    ).resolves.toEqual({
      path: '.workspace/releases/text-segmentation-1.0.0.package.json',
      nativePath: '/tmp/workspace/.workspace/releases/text-segmentation-1.0.0.package.json',
      hash: 'package-hash',
      bytesWritten: 512,
    })

    expect(mockInvoke).toHaveBeenCalledWith('publish_package_writer', {
      workspaceRoot: '/tmp/workspace',
      relativePath: '.workspace/releases/text-segmentation-1.0.0.package.json',
      releaseVersion: '1.0.0',
      contentHash: `sha256:${'a'.repeat(64)}`,
      manifestRef: 'product/releases/text-segmentation/1.0.0.json',
      artifactRef: {
        artifact_id: 'text-segmentation',
        store: 'product',
        content_hash: `sha256:${'a'.repeat(64)}`,
        manifest_ref: 'product/manifests/text-segmentation.json',
      },
    })
  })
})

describe('legacy golden baseline writer', () => {
  it('does not expose the obsolete dedicated writeGoldenBaseline helper', () => {
    expect(tauriModule).not.toHaveProperty('writeGoldenBaseline')
  })
})

describe('deleteWorkspacePath', () => {
  it('passes workspaceRoot and path to the Tauri deleter', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockResolvedValue(undefined)

    await expect(
      deleteWorkspacePath('/tmp/workspace', '.workspace/import_files/case.json'),
    ).resolves.toBeUndefined()

    expect(mockInvoke).toHaveBeenCalledWith('delete_workspace_path', {
      workspaceRoot: '/tmp/workspace',
      path: '.workspace/import_files/case.json',
    })
  })

  it('uses the native deleter when only the sidecar is degraded', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeDegraded()
    mockInvoke.mockResolvedValue(undefined)

    await expect(
      deleteWorkspacePath('/tmp/workspace', '.workspace/import_files/case.json'),
    ).resolves.toBeUndefined()

    expect(mockInvoke).toHaveBeenCalledWith('delete_workspace_path', {
      workspaceRoot: '/tmp/workspace',
      path: '.workspace/import_files/case.json',
    })
  })
})

describe('safe-write native helpers', () => {
  it('uses Tauri IPC for read, checkpoint, seed, restore, and clear when only sidecar is degraded', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeDegraded()
    mockInvoke.mockImplementation(async (command) => {
      if (command === 'read_workspace_file') {
        return { path: 'GRAPH.md', content: 'graph body', hash: 'native-hash' }
      }
      if (command === 'checkpoint_workspace_file') {
        return { path: 'GRAPH.md', existed: true, created: true }
      }
      if (command === 'seed_workspace_checkpoint') {
        return { path: 'GRAPH.md', existed: true, created: true }
      }
      if (command === 'restore_workspace_file') {
        return { path: 'GRAPH.md', existed: true, content: 'before body' }
      }
      return undefined
    })

    await expect(readWorkspaceFile('/tmp/workspace', 'GRAPH.md')).resolves.toEqual({
      path: 'GRAPH.md',
      content: 'graph body',
      hash: 'native-hash',
    })
    await expect(checkpointWorkspaceFile('/tmp/workspace', 'GRAPH.md')).resolves.toEqual({
      path: 'GRAPH.md',
      existed: true,
      created: true,
    })
    await expect(
      seedWorkspaceCheckpoint('/tmp/workspace', 'GRAPH.md', 'before body', true),
    ).resolves.toEqual({
      path: 'GRAPH.md',
      existed: true,
      created: true,
    })
    await expect(restoreWorkspaceFile('/tmp/workspace', 'GRAPH.md')).resolves.toEqual({
      path: 'GRAPH.md',
      existed: true,
      content: 'before body',
    })
    await expect(clearWorkspaceCheckpoint('/tmp/workspace', 'GRAPH.md')).resolves.toBeUndefined()

    expect(mockInvoke).toHaveBeenNthCalledWith(1, 'read_workspace_file', {
      workspaceRoot: '/tmp/workspace',
      path: 'GRAPH.md',
    })
    expect(mockInvoke).toHaveBeenNthCalledWith(2, 'checkpoint_workspace_file', {
      workspaceRoot: '/tmp/workspace',
      path: 'GRAPH.md',
    })
    expect(mockInvoke).toHaveBeenNthCalledWith(3, 'seed_workspace_checkpoint', {
      workspaceRoot: '/tmp/workspace',
      path: 'GRAPH.md',
      content: 'before body',
      existed: true,
    })
    expect(mockInvoke).toHaveBeenNthCalledWith(4, 'restore_workspace_file', {
      workspaceRoot: '/tmp/workspace',
      path: 'GRAPH.md',
    })
    expect(mockInvoke).toHaveBeenNthCalledWith(5, 'clear_workspace_checkpoint', {
      workspaceRoot: '/tmp/workspace',
      path: 'GRAPH.md',
    })
  })

  it('rejects clearWorkspaceCheckpoint outside Tauri instead of silently succeeding', async () => {
    vi.stubGlobal('window', { location: { origin: 'http://localhost:5173' } })
    await resetRuntimeForTest()

    await expect(clearWorkspaceCheckpoint('/tmp/workspace', 'GRAPH.md')).rejects.toThrow(
      'Desktop only',
    )

    expect(mockInvoke).not.toHaveBeenCalled()
  })
})

describe('skill workspace native helpers', () => {
  it('creates a skill via the Rust writer and maps the snake_case result', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockResolvedValue({ root: '/tmp/Skills/demo', skill_id: 'demo' })

    await expect(createSkillWorkspace('/tmp/Skills', 'demo')).resolves.toEqual({
      root: '/tmp/Skills/demo',
      skillId: 'demo',
    })

    expect(mockInvoke).toHaveBeenCalledWith('create_skill_workspace', {
      parentDirectory: '/tmp/Skills',
      skillId: 'demo',
    })
  })

  it('passes a blank parent through so Rust defaults to the config Skills dir', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockResolvedValue({ root: '/cfg/Skills/demo', skill_id: 'demo' })

    await expect(createSkillWorkspace('', 'demo')).resolves.toEqual({
      root: '/cfg/Skills/demo',
      skillId: 'demo',
    })

    expect(mockInvoke).toHaveBeenCalledWith('create_skill_workspace', {
      parentDirectory: '',
      skillId: 'demo',
    })
  })

  it('rejects createSkillWorkspace outside the desktop runtime', async () => {
    vi.stubGlobal('window', { location: { origin: 'http://localhost:5173' } })
    await resetRuntimeForTest()

    await expect(createSkillWorkspace('/tmp/Skills', 'demo')).rejects.toThrow('Desktop only')
    expect(mockInvoke).not.toHaveBeenCalled()
  })

  it('opens a folder via the Rust writer and maps the snake_case result', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockResolvedValue({ root: '/tmp/opened', skill_id: 'opened' })

    await expect(openSkillWorkspace('/tmp/opened')).resolves.toEqual({
      root: '/tmp/opened',
      skillId: 'opened',
    })

    expect(mockInvoke).toHaveBeenCalledWith('open_skill_workspace', { directory: '/tmp/opened' })
  })

  it('checks workspace path existence via the Rust read-only command', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    await markRuntimeReady()
    mockInvoke.mockResolvedValue(false)

    await expect(workspacePathExists('/tmp/gone')).resolves.toBe(false)

    expect(mockInvoke).toHaveBeenCalledWith('workspace_path_exists', { path: '/tmp/gone' })
  })

  it('keeps the MRU intact by returning true when the native check is unavailable', async () => {
    vi.stubGlobal('window', { location: { origin: 'http://localhost:5173' } })
    await resetRuntimeForTest()

    await expect(workspacePathExists('/tmp/whatever')).resolves.toBe(true)
    expect(mockInvoke).not.toHaveBeenCalled()
  })
})
