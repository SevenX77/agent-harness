import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PublishResult } from '@/api/types'
import { TooltipProvider } from '@/components/ui/tooltip'
import { revealInFileManager, writePublishPackage } from '@/lib/tauri'
import {
  executePackageRelease,
  Header,
  packageRelativePath,
  type HeaderReleaseIdentity,
} from './Header'

const publishHookState = vi.hoisted(() => ({
  lastResult: null as PublishResult | null,
}))

vi.mock('@/hooks/useSkillSync', () => ({
  useSkillSync: () => ({
    status: 'idle',
    save: vi.fn(),
    sync: vi.fn(),
    submit: vi.fn(),
  }),
}))

vi.mock('@/hooks/usePublishSkill', () => ({
  usePublishSkill: () => ({
    status: 'success',
    error: null,
    publish: vi.fn(),
    lastResult: publishHookState.lastResult,
  }),
}))

vi.mock('@/lib/tauri', () => ({
  revealInFileManager: vi.fn(),
  writePublishPackage: vi.fn(),
}))

const mockWritePublishPackage = vi.mocked(writePublishPackage)
const mockRevealInFileManager = vi.mocked(revealInFileManager)

interface CapturedToastAction {
  label: string
  onClick: () => void | Promise<void>
}

interface CapturedToastOptions {
  description?: string
  action?: CapturedToastAction
}

function createToastApiCapture() {
  const success = vi.fn((message: string, options?: unknown) => ({ message, options }))
  const error = vi.fn((message: string, options?: unknown) => ({ message, options }))
  return { toastApi: { success, error }, success, error }
}

function isToastAction(value: unknown): value is CapturedToastAction {
  return (
    typeof value === 'object' &&
    value !== null &&
    'label' in value &&
    'onClick' in value &&
    typeof value.onClick === 'function' &&
    typeof value.label === 'string'
  )
}

function getToastAction(options: unknown, expectedLabel: string): CapturedToastAction {
  const action =
    typeof options === 'object' && options !== null && 'action' in options
      ? (options as CapturedToastOptions).action
      : undefined
  if (!isToastAction(action)) {
    throw new Error(`Expected toast action "${expectedLabel}"`)
  }
  expect(action.label).toBe(expectedLabel)
  return action
}

async function clickToastAction(options: unknown, label: string) {
  const action = getToastAction(options, label)
  await action.onClick()
  await Promise.resolve()
}

function committedReleaseResult(): PublishResult {
  return {
    status: 'ok',
    message: 'Published to local product store',
    artifact_id: 'text-segmentation',
    extra: {
      release_version: '1.0.0',
      artifact_id: 'text-segmentation',
      content_hash: `sha256:${'a'.repeat(64)}`,
      manifest_ref: 'manifests/text-segmentation.json',
      artifact_ref: {
        artifact_id: 'text-segmentation',
        content_hash: `sha256:${'a'.repeat(64)}`,
        manifest_ref: 'manifests/text-segmentation.json',
        store: 'product',
      },
      remote_sync: {
        status: 'skipped',
        reason: 'registry_not_configured',
      },
    },
  }
}

function releaseIdentity(): HeaderReleaseIdentity {
  return {
    releaseVersion: '1.0.0',
    artifactId: 'text-segmentation',
    contentHash: `sha256:${'a'.repeat(64)}`,
    manifestRef: 'product/releases/text-segmentation/1.0.0.json',
    artifactRef: {
      artifact_id: 'text-segmentation',
      content_hash: `sha256:${'a'.repeat(64)}`,
      manifest_ref: 'product/manifests/text-segmentation.json',
      store: 'product',
    },
    remoteSyncLabel: 'remote sync skipped',
    a11yLabel: `Release 1.0.0, text-segmentation, sha256:${'a'.repeat(64)}, product/releases/text-segmentation/1.0.0.json, remote sync skipped`,
  }
}

describe('Header release status', () => {
  beforeEach(() => {
    publishHookState.lastResult = committedReleaseResult()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('shows committed release identity after a successful release', () => {
    const html = renderToStaticMarkup(
      <TooltipProvider>
        <Header
          skillId="text-segmentation"
          workspaceRoot="/tmp/workspace"
          copilotOpen={false}
          onCopilotToggle={vi.fn()}
          onHome={vi.fn()}
        />
      </TooltipProvider>,
    )

    expect(html).toContain('Release 1.0.0')
    expect(html).toContain('text-segmentation')
    expect(html).toContain(`sha256:${'a'.repeat(64)}`)
    expect(html).toContain('manifests/text-segmentation.json')
    expect(html).toContain('remote sync skipped')
  })

  it('does not render a release badge from top-level artifact_id alone', () => {
    publishHookState.lastResult = {
      status: 'ok',
      message: 'Published to registry',
      artifact_id: 'art-999',
      extra: {
        release_version: '1.0.0',
        content_hash: `sha256:${'b'.repeat(64)}`,
        manifest_ref: 'manifests/text-segmentation.json',
      },
    }

    const html = renderToStaticMarkup(
      <TooltipProvider>
        <Header
          skillId="text-segmentation"
          workspaceRoot="/tmp/workspace"
          copilotOpen={false}
          onCopilotToggle={vi.fn()}
          onHome={vi.fn()}
        />
      </TooltipProvider>,
    )

    expect(html).not.toContain('Release 1.0.0')
    expect(html).not.toContain('art-999')
  })

  it('uses artifact_ref artifact_id instead of inconsistent extra artifact_id', () => {
    publishHookState.lastResult = {
      status: 'ok',
      message: 'Published to local product store',
      artifact_id: 'response-artifact-id',
      extra: {
        release_version: '1.0.0',
        artifact_id: 'stale-extra-artifact',
        content_hash: `sha256:${'c'.repeat(64)}`,
        manifest_ref: 'manifests/release-manifest.json',
        artifact_ref: {
          artifact_id: 'artifact-ref-source',
          content_hash: `sha256:${'c'.repeat(64)}`,
          manifest_ref: 'manifests/release-manifest.json',
          store: 'product',
        },
      },
    }

    const html = renderToStaticMarkup(
      <TooltipProvider>
        <Header
          skillId="draft-skill"
          workspaceRoot="/tmp/workspace"
          copilotOpen={false}
          onCopilotToggle={vi.fn()}
          onHome={vi.fn()}
        />
      </TooltipProvider>,
    )

    expect(html).toContain('Release 1.0.0')
    expect(html).toContain('artifact-ref-source')
    expect(html).not.toContain('stale-extra-artifact')
  })

  it('exposes the Team menu trigger that gates the Artifact Registry release actions', () => {
    const html = renderToStaticMarkup(
      <TooltipProvider>
        <Header
          skillId="text-segmentation"
          workspaceRoot="/tmp/workspace"
          copilotOpen={false}
          onCopilotToggle={vi.fn()}
          onHome={vi.fn()}
        />
      </TooltipProvider>,
    )

    // Per repo convention, dropdown CONTENT (Save to Team / the
    // `Artifact Registry (not git push)` separator+label / Release) lives in a
    // Radix portal and is NOT emitted by renderToStaticMarkup, so the in-menu
    // disambiguation (#5) is verified by the desktop screenshot + e2e, not here.
    // This render-contract test locks that the Team menu trigger is present.
    expect(html).toContain('data-slot="dropdown-menu-trigger"')
    expect(html).toContain('Team')
  })

  it('offers a native-fs Package release action only after release identity is complete', () => {
    const html = renderToStaticMarkup(
      <TooltipProvider>
        <Header
          skillId="draft-skill"
          workspaceRoot="/tmp/workspace"
          copilotOpen={false}
          onCopilotToggle={vi.fn()}
          onHome={vi.fn()}
        />
      </TooltipProvider>,
    )

    expect(html).toContain('Package release')
    expect(html).not.toContain('Download zip')
  })
})

describe('executePackageRelease', () => {
  beforeEach(() => {
    mockWritePublishPackage.mockReset()
    mockRevealInFileManager.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('writes through native-fs and exposes the returned native path in the success toast reveal action', async () => {
    const { toastApi, success } = createToastApiCapture()
    mockWritePublishPackage.mockResolvedValue({
      path: '.workspace/releases/text-segmentation-1.0.0.package.json',
      nativePath: '/tmp/workspace/.workspace/releases/text-segmentation-1.0.0.package.json',
      hash: 'package-hash',
      bytesWritten: 512,
    })

    await executePackageRelease({
      skillId: 'text-segmentation',
      workspaceRoot: '/tmp/workspace',
      releaseIdentity: releaseIdentity(),
      toastApi,
    })

    expect(mockWritePublishPackage).toHaveBeenCalledWith({
      workspaceRoot: '/tmp/workspace',
      relativePath: '.workspace/releases/text-segmentation-1.0.0.package.json',
      releaseVersion: '1.0.0',
      contentHash: `sha256:${'a'.repeat(64)}`,
      manifestRef: 'product/releases/text-segmentation/1.0.0.json',
      artifactRef: releaseIdentity().artifactRef,
    })
    expect(success).toHaveBeenCalledWith(
      expect.stringContaining('Packaged release 1.0.0'),
      expect.objectContaining({
        description: '/tmp/workspace/.workspace/releases/text-segmentation-1.0.0.package.json',
        action: expect.objectContaining({ label: 'Reveal' }),
      }),
    )

    await clickToastAction(success.mock.calls[0]?.[1], 'Reveal')
    expect(mockRevealInFileManager).toHaveBeenCalledWith(
      '/tmp/workspace/.workspace/releases/text-segmentation-1.0.0.package.json',
    )
  })

  it.each([
    ['Conflict', 'native-fs conflict'],
    ['PermissionDenied', 'native-fs permission'],
    ['PathEscape', 'native-fs path_escape'],
  ])('allows choosing a new target path after a native-fs %s error and retries the package writer', async (type, messagePrefix) => {
    const { toastApi, success, error } = createToastApiCapture()
    const initialPath = packageRelativePath('text-segmentation', '1.0.0')
    const retryPath = '.workspace/releases/text-segmentation-1.0.0-copy.package.json'
    const chooseTargetPath = vi.fn(() => retryPath)
    mockWritePublishPackage
      .mockRejectedValueOnce({ type, data: { path: initialPath } })
      .mockResolvedValueOnce({
        path: retryPath,
        nativePath: `/tmp/workspace/${retryPath}`,
        hash: 'package-hash',
        bytesWritten: 512,
      })

    await executePackageRelease({
      skillId: 'text-segmentation',
      workspaceRoot: '/tmp/workspace',
      releaseIdentity: releaseIdentity(),
      toastApi,
      chooseTargetPath,
    })

    expect(error).toHaveBeenCalledWith(
      `${messagePrefix}: ${initialPath}`,
      expect.objectContaining({
        action: expect.objectContaining({ label: 'Choose path' }),
      }),
    )

    await clickToastAction(error.mock.calls[0]?.[1], 'Choose path')

    expect(chooseTargetPath).toHaveBeenCalledWith(initialPath)
    expect(mockWritePublishPackage).toHaveBeenLastCalledWith(
      expect.objectContaining({ relativePath: retryPath }),
    )
    expect(success).toHaveBeenCalledWith(
      expect.stringContaining('Packaged release 1.0.0'),
      expect.objectContaining({ description: `/tmp/workspace/${retryPath}` }),
    )
  })

  it('does not fall back to window.prompt for package target rechoose', async () => {
    const { toastApi, error } = createToastApiCapture()
    const prompt = vi.fn(() => '.workspace/releases/prompt.package.json')
    vi.stubGlobal('window', { prompt })
    mockWritePublishPackage.mockRejectedValueOnce({
      type: 'Conflict',
      data: { path: '.workspace/releases/release.package.json' },
    })

    await executePackageRelease({
      skillId: 'text-segmentation',
      workspaceRoot: '/tmp/workspace',
      releaseIdentity: releaseIdentity(),
      toastApi,
    })

    await clickToastAction(error.mock.calls[0]?.[1], 'Choose path')

    expect(prompt).not.toHaveBeenCalled()
    expect(mockWritePublishPackage).toHaveBeenCalledTimes(1)
  })

  it.each([
    [
      'PermissionDenied',
      '.workspace/releases/release.package.json',
      'native-fs permission: .workspace/releases/release.package.json',
    ],
    [
      'PathEscape',
      '../release.package.json',
      'native-fs path_escape: ../release.package.json',
    ],
  ])('shows typed native-fs %s errors with a rechoose action and without generic release failure copy', async (type, path, message) => {
    const { toastApi, error } = createToastApiCapture()
    mockWritePublishPackage.mockRejectedValue({ type, data: { path } })

    await executePackageRelease({
      skillId: 'text-segmentation',
      workspaceRoot: '/tmp/workspace',
      releaseIdentity: releaseIdentity(),
      toastApi,
    })

    expect(error).toHaveBeenCalledWith(
      message,
      expect.objectContaining({
        action: expect.objectContaining({ label: 'Choose path' }),
      }),
    )
    expect(error).not.toHaveBeenCalledWith(
      expect.stringContaining('Release validation failed'),
      expect.anything(),
    )
  })
})
