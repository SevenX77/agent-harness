import { renderToStaticMarkup } from 'react-dom/server'
import type { ComponentProps, ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type { CopilotSession } from '../../store/copilotStore'
import { SessionTabs, SessionTabsView, consumeHorizontalWheel, sessionTabLabel, sessionTabs } from './session-tabs'

vi.mock('@/components/ui/button', () => ({
  Button: ({
    children,
    ...props
  }: ComponentProps<'button'> & { children: ReactNode }) => (
    <button data-slot="button" {...props}>
      {children}
    </button>
  ),
}))

vi.mock('@/lib/utils', () => ({
  cn: (...classes: Array<string | false | null | undefined>) => classes.filter(Boolean).join(' '),
}))

function session(id: string, messages: Array<{ role: 'user' | 'assistant'; content: string }>): CopilotSession {
  return {
    id,
    messages: messages.map((m, i) => ({ id: `${id}-${i}`, role: m.role, content: m.content }) as never),
  }
}

describe('sessionTabLabel', () => {
  it('uses the first user message first line as the label', () => {
    expect(sessionTabLabel(session('s1', [{ role: 'user', content: 'How do I add a node?\nmore' }]), 0)).toBe(
      'How do I add a node?',
    )
  })

  it('truncates long first messages', () => {
    const label = sessionTabLabel(
      session('s1', [{ role: 'user', content: 'a'.repeat(40) }]),
      0,
    )
    expect(label).toBe(`${'a'.repeat(24)}…`)
  })

  it('falls back to a 1-based Chat N when there is no user turn', () => {
    expect(sessionTabLabel(session('s1', []), 0)).toBe('Chat 1')
    expect(sessionTabLabel(session('s2', [{ role: 'assistant', content: 'hi' }]), 1)).toBe('Chat 2')
  })
})

describe('sessionTabs', () => {
  it('maps sessions to tabs, marking the active one', () => {
    const tabs = sessionTabs(
      [session('s1', [{ role: 'user', content: 'first' }]), session('s2', [])],
      's2',
    )

    expect(tabs).toEqual([
      { id: 's1', label: 'first', isActive: false },
      { id: 's2', label: 'Chat 2', isActive: true },
    ])
  })

  it('marks no tab active when activeSessionId is null', () => {
    const tabs = sessionTabs([session('s1', [])], null)
    expect(tabs.every((tab) => !tab.isActive)).toBe(true)
  })
})

describe('SessionTabs', () => {
  it('renders a tab per session plus a chat actions control', () => {
    const html = renderToStaticMarkup(
      <SessionTabs
        sessions={[
          session('s1', [{ role: 'user', content: 'first question' }]),
          session('s2', [{ role: 'user', content: 'second question' }]),
        ]}
        activeSessionId="s1"
        onSwitch={() => undefined}
        onNew={() => undefined}
        onRestore={() => undefined}
        onClose={() => undefined}
      />,
    )

    expect(html).toContain('first question')
    expect(html).toContain('second question')
    expect(html).toContain('aria-label="Chat actions"')
  })

  it('renders nothing for a single empty session (no switcher needed)', () => {
    const html = renderToStaticMarkup(
      <SessionTabs
        sessions={[session('s1', [])]}
        activeSessionId="s1"
        onSwitch={() => undefined}
        onNew={() => undefined}
        onRestore={() => undefined}
        onClose={() => undefined}
      />,
    )

    expect(html).toBe('')
  })

  it('still renders for a single non-empty session so a new chat can be started', () => {
    const html = renderToStaticMarkup(
      <SessionTabs
        sessions={[session('s1', [{ role: 'user', content: 'only chat' }])]}
        activeSessionId="s1"
        onSwitch={() => undefined}
        onNew={() => undefined}
        onRestore={() => undefined}
        onClose={() => undefined}
      />,
    )

    expect(html).toContain('only chat')
    expect(html).toContain('aria-label="Chat actions"')
  })

  // Buttons are wrapped in Tooltip/TooltipTrigger now, so interaction tests walk
  // the element tree instead of hardcoding children indices.
  type AnyElement = { key?: string | null; props?: Record<string, unknown> & { children?: unknown } }

  function collectElements(node: unknown, out: AnyElement[] = []): AnyElement[] {
    if (Array.isArray(node)) {
      node.forEach((child) => collectElements(child, out))
      return out
    }
    if (!node || typeof node !== 'object') return out
    const el = node as AnyElement
    out.push(el)
    if (el.props && 'children' in el.props) collectElements(el.props.children, out)
    return out
  }

  function textContent(node: unknown): string {
    if (typeof node === 'string' || typeof node === 'number') return String(node)
    if (Array.isArray(node)) return node.map(textContent).join('')
    if (!node || typeof node !== 'object') return ''
    const el = node as AnyElement
    return textContent(el.props?.children)
  }

  it('calls onSwitch with the chosen session id', () => {
    const onSwitch = vi.fn()
    const element = SessionTabsView({
      sessions: [session('s1', [{ role: 'user', content: 'a' }]), session('s2', [{ role: 'user', content: 'b' }])],
      activeSessionId: 's1',
      onSwitch,
      onNew: () => undefined,
      onRestore: () => undefined,
      onClose: () => undefined,
    })

    const all = collectElements(element)
    const secondTab = all.find((el) => el.key === 's2')
    const labelButton = collectElements(secondTab).find((el) => typeof el.props?.onClick === 'function')
    ;(labelButton?.props?.onClick as () => void)?.()

    expect(onSwitch).toHaveBeenCalledWith('s2')
  })

  it('calls onNew when the New chat menu item is activated', () => {
    const onNew = vi.fn()
    const element = SessionTabsView({
      sessions: [session('s1', [{ role: 'user', content: 'a' }]), session('s2', [{ role: 'user', content: 'b' }])],
      activeSessionId: 's1',
      onSwitch: () => undefined,
      onNew,
      onRestore: () => undefined,
      onClose: () => undefined,
    })

    const newItem = collectElements(element).find(
      (el) => typeof el.props?.onSelect === 'function' && textContent(el).includes('New chat'),
    )
    ;(newItem?.props?.onSelect as () => void)?.()

    expect(onNew).toHaveBeenCalledTimes(1)
  })

  it('calls onRestore when the Restore chat menu item is activated', () => {
    const onRestore = vi.fn()
    const element = SessionTabsView({
      sessions: [session('s1', [{ role: 'user', content: 'a' }]), session('s2', [{ role: 'user', content: 'b' }])],
      activeSessionId: 's1',
      onSwitch: () => undefined,
      onNew: () => undefined,
      onRestore,
      onClose: () => undefined,
    })

    const restoreItem = collectElements(element).find(
      (el) => typeof el.props?.onSelect === 'function' && textContent(el).includes('Restore chat'),
    )
    ;(restoreItem?.props?.onSelect as () => void)?.()

    expect(onRestore).toHaveBeenCalledTimes(1)
  })
})


// R5-B: vertical wheel on the tab strip scrolls it horizontally (F1 constraint).
describe('consumeHorizontalWheel', () => {
  function viewport(overrides: Partial<{ scrollLeft: number; scrollWidth: number; clientWidth: number }> = {}) {
    return { scrollLeft: 0, scrollWidth: 400, clientWidth: 200, ...overrides }
  }

  it('translates dominant vertical wheel into horizontal scroll and consumes it', () => {
    const vp = viewport()
    expect(consumeHorizontalWheel(vp, 0, 40)).toBe(true)
    expect(vp.scrollLeft).toBe(40)
    expect(consumeHorizontalWheel(vp, 0, -15)).toBe(true)
    expect(vp.scrollLeft).toBe(25)
  })

  it('does nothing when the strip has no horizontal overflow', () => {
    const vp = viewport({ scrollWidth: 200 })
    expect(consumeHorizontalWheel(vp, 0, 40)).toBe(false)
    expect(vp.scrollLeft).toBe(0)
  })

  it('leaves native horizontal wheel gestures to the browser', () => {
    const vp = viewport()
    expect(consumeHorizontalWheel(vp, 40, 10)).toBe(false)
    expect(vp.scrollLeft).toBe(0)
  })
})

describe('SessionTabs close button', () => {
  it('renders a close control per tab', () => {
    const html = renderToStaticMarkup(
      <SessionTabs
        sessions={[
          session('a', [{ role: 'user', content: 'hello world' }]),
          session('b', []),
        ]}
        activeSessionId="a"
        onSwitch={() => undefined}
        onNew={() => undefined}
        onRestore={() => undefined}
        onClose={() => undefined}
      />,
    )
    expect(html).toContain('aria-label="Close hello world"')
    expect(html).toContain('aria-label="Close Chat 2"')
  })
})
