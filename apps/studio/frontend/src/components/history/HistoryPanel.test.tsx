// @vitest-environment jsdom
import { renderToStaticMarkup } from 'react-dom/server'
import { act, createElement, isValidElement, type ComponentProps, type ReactElement, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { GitHistoryItem, SkillDetail } from '../../api/types'
import { HistoryPanel, LocalHistoryPanelView, type LocalHistoryPanelViewProps } from './HistoryPanel'

// React 19's act() warns unless the environment opts in.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

// T-n6hist test#4 (n6-history revert): the integration boundary lives in the
// HistoryPanel container + useLocalHistory hook, so we mock the SWR-backed hook to
// expose a controllable `revert` spy and assert the wiring end-to-end. The pure
// view (LocalHistoryPanelView) is render-tested separately below via SSR.
const historyMocks = vi.hoisted(() => ({
  revert: vi.fn(),
  refresh: vi.fn(),
  history: [] as GitHistoryItem[],
}))

const toastMocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
}))

vi.mock('../../hooks/useRunHistory', () => ({
  useLocalHistory: () => ({
    history: historyMocks.history,
    isLoading: false,
    error: null,
    refresh: historyMocks.refresh,
    revert: historyMocks.revert,
  }),
}))

vi.mock('sonner', () => ({
  toast: toastMocks,
}))

vi.mock('../ui/button', () => ({
  Button: ({
    children,
    ...props
  }: ComponentProps<'button'> & { children: ReactNode }) => (
    <button data-slot="button" {...props}>
      {children}
    </button>
  ),
}))

const snapshots: GitHistoryItem[] = [
  {
    sha: 'abc1234567890',
    message: 'auto-run: success',
    author: 'studio-user',
    timestamp: '2026-05-13T12:00:00Z',
    kind: 'auto_run',
  },
]

function baseProps(overrides: Partial<LocalHistoryPanelViewProps> = {}): LocalHistoryPanelViewProps {
  return {
    history: [],
    isLoading: false,
    error: null,
    selectedSha: null,
    revertingSha: null,
    onSelect: vi.fn(),
    onRefresh: vi.fn(),
    onRevert: vi.fn(),
    ...overrides,
  }
}

function textOf(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === 'boolean') {
    return ''
  }
  if (typeof node === 'string' || typeof node === 'number') {
    return String(node)
  }
  if (Array.isArray(node)) {
    return node.map(textOf).join('')
  }
  if (isValidElement(node)) {
    return textOf((node as ReactElement<{ children?: ReactNode }>).props.children)
  }
  return ''
}

function findButtonByText(
  node: ReactNode,
  label: string,
): ReactElement<{ children?: ReactNode; disabled?: boolean; onClick?: () => void }> | null {
  if (!isValidElement(node)) {
    return null
  }

  const element = node as ReactElement<{ children?: ReactNode; disabled?: boolean; onClick?: () => void }>
  if (element.props.onClick && textOf(element.props.children).includes(label)) {
    return element
  }

  const children = element.props.children
  if (Array.isArray(children)) {
    for (const child of children) {
      const match = findButtonByText(child, label)
      if (match) {
        return match
      }
    }
  }
  return findButtonByText(children, label)
}

describe('LocalHistoryPanelView', () => {
  it('renders empty local history state', () => {
    const html = renderToStaticMarkup(<LocalHistoryPanelView {...baseProps()} />)

    expect(html).toContain('No local history snapshots yet.')
    expect(html).toContain('data-slot="button"')
  })

  it('renders loading state', () => {
    const html = renderToStaticMarkup(<LocalHistoryPanelView {...baseProps({ isLoading: true })} />)

    expect(html).toContain('Loading local history...')
  })

  it('renders load failure state', () => {
    const html = renderToStaticMarkup(<LocalHistoryPanelView {...baseProps({ error: new Error('history failed') })} />)

    expect(html).toContain('history failed')
  })

  it('renders release snapshots with a release kind label', () => {
    const html = renderToStaticMarkup(
      <LocalHistoryPanelView
        {...baseProps({
          history: [
            {
              sha: 'release1234567890',
              message: 'release-1.0.0',
              author: 'studio-user',
              timestamp: '2026-05-13T12:00:00Z',
              kind: 'release',
              release_version: '1.0.0',
            },
          ],
        })}
      />,
    )

    expect(html).toContain('Release')
    expect(html).not.toContain('Other')
  })

  it('calls revert for the selected snapshot', () => {
    const onRevert = vi.fn()
    const element = LocalHistoryPanelView(baseProps({ history: snapshots, selectedSha: snapshots[0].sha, onRevert }))
    const button = findButtonByText(element, 'Revert')

    button?.props.onClick?.()

    expect(onRevert).toHaveBeenCalledWith(snapshots[0].sha)
  })

  it('disables revert for manifest-only release snapshots', () => {
    const onRevert = vi.fn()
    const manifestOnlyRelease = {
      sha: 'release:1.0.0:sha256abc',
      message: 'release-1.0.0',
      author: 'product-store',
      timestamp: '2026-05-13T12:00:00Z',
      kind: 'release',
      release_version: '1.0.0',
      source: 'manifest',
      revertable: false,
    } as GitHistoryItem
    const element = LocalHistoryPanelView(
      baseProps({ history: [manifestOnlyRelease], selectedSha: manifestOnlyRelease.sha, onRevert }),
    )
    const button = findButtonByText(element, 'Revert')

    expect(button?.props.disabled).toBe(true)
    button?.props.onClick?.()
    expect(onRevert).not.toHaveBeenCalled()
  })
})

// T-n6hist test#4: container-level integration. Render the real HistoryPanel
// (which owns selection + handleRevert + toasts) against a mocked useLocalHistory
// whose `revert` is a controllable spy, and drive a real DOM click so the effect
// chain runs (renderToStaticMarkup never runs effects, so this needs jsdom + act).
describe('HistoryPanel revert flow (integration)', () => {
  let container: HTMLDivElement
  let root: ReturnType<typeof createRoot>

  beforeEach(() => {
    historyMocks.revert.mockReset()
    historyMocks.refresh.mockReset()
    historyMocks.history = [
      {
        sha: 'abc1234567890',
        message: 'auto-run: success',
        author: 'studio-user',
        timestamp: '2026-05-13T12:00:00Z',
        kind: 'auto_run',
      },
    ]
    toastMocks.success.mockReset()
    toastMocks.error.mockReset()
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
  })

  function render() {
    act(() => {
      root.render(createElement(HistoryPanel, { skillId: 'writer-smoke' }))
    })
  }

  function clickByText(label: string): HTMLButtonElement {
    const button = Array.from(container.querySelectorAll('button')).find((node) =>
      (node.textContent ?? '').includes(label),
    )
    if (!button) {
      throw new Error(`No button found with label ${label}`)
    }
    act(() => {
      button.dispatchEvent(new window.MouseEvent('click', { bubbles: true }))
    })
    return button as HTMLButtonElement
  }

  it('selects then reverts the chosen snapshot, toasting success and refreshing detail via the hook', async () => {
    const detail = { manifest: { name: 'writer-smoke' } } as unknown as SkillDetail
    historyMocks.revert.mockResolvedValue(detail)

    render()
    // Select the snapshot, then Revert.
    clickByText('auto-run: success')
    let resolveRevert: (value: SkillDetail) => void = () => {}
    historyMocks.revert.mockImplementation(
      () =>
        new Promise<SkillDetail>((resolve) => {
          resolveRevert = resolve
        }),
    )
    clickByText('Revert')

    expect(historyMocks.revert).toHaveBeenCalledWith('abc1234567890')

    await act(async () => {
      resolveRevert(detail)
      await Promise.resolve()
    })

    expect(toastMocks.success).toHaveBeenCalledWith('Reverted to local history snapshot')
    expect(toastMocks.error).not.toHaveBeenCalled()
  })

  it('surfaces a GIT_REVERT_CONFLICT as an error toast (never silent)', async () => {
    render()
    clickByText('auto-run: success')

    let rejectRevert: (reason: unknown) => void = () => {}
    historyMocks.revert.mockImplementation(
      () =>
        new Promise<SkillDetail>((_resolve, reject) => {
          rejectRevert = reject
        }),
    )
    clickByText('Revert')

    expect(historyMocks.revert).toHaveBeenCalledWith('abc1234567890')

    await act(async () => {
      rejectRevert(new Error('GIT_REVERT_CONFLICT: working tree has uncommitted changes'))
      await Promise.resolve()
    })

    expect(toastMocks.error).toHaveBeenCalledWith(
      expect.stringContaining('GIT_REVERT_CONFLICT'),
    )
    expect(toastMocks.success).not.toHaveBeenCalled()
  })
})
