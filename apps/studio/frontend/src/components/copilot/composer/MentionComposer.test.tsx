// @vitest-environment jsdom

/** Typing `@` opens the menu, and picking a row leaves a pill behind.
 *
 * Design: `copilot-assist/mvp1-alignment.md` F4 ① + decision COPILOT_ASSIST-10.
 *
 * The pure halves are tested next door (`composer-document`, `mention-candidates`).
 * What only shows up here is the wiring: the suggestion plugin turning what is in
 * front of the caret into a query, and a pick turning into an atom the serializer
 * reads back as a mention.
 *
 * The caret is driven through `setText` rather than by faking keystrokes:
 * ProseMirror learns about typing from DOM mutations, which synthetic `input`
 * events do not produce, so a fake keystroke would test nothing. `setText` puts
 * the document and the caret in exactly the state typing leaves them in, and the
 * suggestion plugin re-matches on every transaction either way.
 */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { createRef } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ComposerValue } from './composer-document'
import { MentionComposer, type MentionComposerHandle } from './MentionComposer'
import { buildMentionCandidates } from './mention-candidates'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const CANDIDATES = buildMentionCandidates({
  filePaths: ['GRAPH.md'],
  phases: [
    { id: 'plan', src: 'plan/LOGIC.md', depends_on: [], mode: 'logic' },
    { id: 'draft', src: 'draft/LOGIC.md', depends_on: [], mode: 'logic' },
  ],
  diagnostics: [],
  trace: null,
})

let container: HTMLDivElement
let root: Root
let latest: ComposerValue | null
let sent: number

function mount() {
  const ref = createRef<MentionComposerHandle>()
  act(() => {
    root.render(
      <MentionComposer
        ref={ref}
        candidates={CANDIDATES}
        placeholder="say something"
        onChange={(value) => {
          latest = value
        }}
        onSend={() => {
          sent += 1
        }}
      />,
    )
  })
  return ref
}

const option = (key: string) =>
  container.querySelector<HTMLElement>(`[data-mention-option="${key}"]`)

describe('MentionComposer', () => {
  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    latest = null
    sent = 0
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  it('shows the placeholder until there is something to send', () => {
    const ref = mount()
    expect(container.textContent).toContain('say something')
    act(() => ref.current?.setText('hello'))
    expect(container.textContent).not.toContain('say something')
  })

  it('reports prepared text as the sentence of the turn', () => {
    const ref = mount()
    act(() => ref.current?.setText('line one\nline two'))
    expect(latest).toEqual({ text: 'line one\nline two', mentions: [] })
  })

  it('opens the menu on `@` and narrows it as the query grows', () => {
    const ref = mount()
    act(() => ref.current?.setText('@'))
    expect(option('phase:plan')).toBeTruthy()
    expect(option('phase:draft')).toBeTruthy()

    act(() => ref.current?.setText('@pla'))
    expect(option('phase:plan')).toBeTruthy()
    expect(option('phase:draft')).toBeNull()
  })

  it('turns a picked row into a mention the turn carries', () => {
    const ref = mount()
    act(() => ref.current?.setText('@plan'))
    const row = option('phase:plan')
    expect(row).toBeTruthy()

    act(() => row?.dispatchEvent(new MouseEvent('click', { bubbles: true })))

    expect(latest?.mentions).toEqual([{ kind: 'phase', ref: 'plan', label: 'plan' }])
    // COPILOT_ASSIST-10 ①: the sentence keeps `@label` where the pill sits, so
    // the query the user typed is REPLACED by the pill rather than left beside it.
    expect(latest?.text.trim()).toBe('@plan')
  })

  it('closes the menu once the pick is made', () => {
    const ref = mount()
    act(() => ref.current?.setText('@plan'))
    act(() => option('phase:plan')?.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    expect(container.querySelector('[data-mention-menu]')).toBeNull()
  })

  it('offers nothing when the query names nothing', () => {
    const ref = mount()
    act(() => ref.current?.setText('@zzzz'))
    expect(container.querySelector('[data-mention-menu]')).toBeNull()
  })

  it('clears back to empty', () => {
    const ref = mount()
    act(() => ref.current?.setText('something'))
    expect(latest?.text).toBe('something')
    act(() => ref.current?.clear())
    expect(container.textContent).toContain('say something')
  })

  it('leaves send alone — the panel decides what a send does', () => {
    mount()
    expect(sent).toBe(0)
  })
})
