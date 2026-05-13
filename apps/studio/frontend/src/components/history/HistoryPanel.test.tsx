import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { isValidElement, type ReactElement, type ReactNode } from 'react'
import type { GitHistoryItem } from '../../api/types'
import { LocalHistoryPanelView, type LocalHistoryPanelViewProps } from './HistoryPanel'

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

function findButtonByText(node: ReactNode, label: string): ReactElement<{ children?: ReactNode; onClick?: () => void }> | null {
  if (!isValidElement(node)) {
    return null
  }

  const element = node as ReactElement<{ children?: ReactNode; onClick?: () => void }>
  if (element.type === 'button' && textOf(element.props.children).includes(label)) {
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
  })

  it('renders loading state', () => {
    const html = renderToStaticMarkup(<LocalHistoryPanelView {...baseProps({ isLoading: true })} />)

    expect(html).toContain('Loading local history...')
  })

  it('renders load failure state', () => {
    const html = renderToStaticMarkup(<LocalHistoryPanelView {...baseProps({ error: new Error('history failed') })} />)

    expect(html).toContain('history failed')
  })

  it('calls revert for the selected snapshot', () => {
    const onRevert = vi.fn()
    const element = LocalHistoryPanelView(baseProps({ history: snapshots, selectedSha: snapshots[0].sha, onRevert }))
    const button = findButtonByText(element, 'Revert')

    button?.props.onClick?.()

    expect(onRevert).toHaveBeenCalledWith(snapshots[0].sha)
  })
})
