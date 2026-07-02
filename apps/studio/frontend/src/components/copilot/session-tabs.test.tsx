import { renderToStaticMarkup } from 'react-dom/server'
import type { ComponentProps, ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type { CopilotSession } from '../../store/copilotStore'
import { SessionTabs, sessionTabLabel, sessionTabs } from './session-tabs'

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
  it('renders a tab per session plus a New chat control', () => {
    const html = renderToStaticMarkup(
      <SessionTabs
        sessions={[
          session('s1', [{ role: 'user', content: 'first question' }]),
          session('s2', [{ role: 'user', content: 'second question' }]),
        ]}
        activeSessionId="s1"
        onSwitch={() => undefined}
        onNew={() => undefined}
        onClose={() => undefined}
      />,
    )

    expect(html).toContain('first question')
    expect(html).toContain('second question')
    expect(html).toContain('aria-label="New chat"')
  })

  it('renders nothing for a single empty session (no switcher needed)', () => {
    const html = renderToStaticMarkup(
      <SessionTabs
        sessions={[session('s1', [])]}
        activeSessionId="s1"
        onSwitch={() => undefined}
        onNew={() => undefined}
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
        onClose={() => undefined}
      />,
    )

    expect(html).toContain('only chat')
    expect(html).toContain('aria-label="New chat"')
  })

  it('calls onSwitch with the chosen session id', () => {
    const onSwitch = vi.fn()
    const element = SessionTabs({
      sessions: [session('s1', [{ role: 'user', content: 'a' }]), session('s2', [{ role: 'user', content: 'b' }])],
      activeSessionId: 's1',
      onSwitch,
      onNew: () => undefined,
      onClose: () => undefined,
    })

    // <div> > [<ScrollArea>{tab spans}</ScrollArea>, <Button new />]; each tab
    // span = [label Button, close Button].
    const props = (element as { props: { children: unknown[] } }).props
    const scrollArea = props.children[0] as {
      props: { children: Array<{ key: string; props: { children: Array<{ props: { onClick?: () => void } }> } }> }
    }
    const secondTab = scrollArea.props.children.find((tab) => tab.key === 's2')
    secondTab?.props.children[0]?.props.onClick?.()

    expect(onSwitch).toHaveBeenCalledWith('s2')
  })

  it('calls onNew when the New chat control is activated', () => {
    const onNew = vi.fn()
    const element = SessionTabs({
      sessions: [session('s1', [{ role: 'user', content: 'a' }]), session('s2', [{ role: 'user', content: 'b' }])],
      activeSessionId: 's1',
      onSwitch: () => undefined,
      onNew,
      onClose: () => undefined,
    })

    const props = (element as { props: { children: unknown[] } }).props
    const newButton = props.children[1] as { props: { onClick?: () => void } }
    newButton.props.onClick?.()

    expect(onNew).toHaveBeenCalledTimes(1)
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
        onClose={() => undefined}
      />,
    )
    expect(html).toContain('aria-label="Close hello world"')
    expect(html).toContain('aria-label="Close Chat 2"')
  })
})
