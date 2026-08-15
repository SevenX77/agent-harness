// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TraceText, traceTextOpenRequest } from './TraceText'
import { WorkspaceProvider, type WorkspaceContextValue } from '../studio/WorkspaceContext'

// React 19's act() warns unless the environment opts in.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

function mockOverflow() {
  Object.defineProperty(HTMLElement.prototype, 'scrollHeight', {
    configurable: true,
    get: () => 400,
  })
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
    configurable: true,
    get: () => 160,
  })
}

afterEach(() => {
  delete (HTMLElement.prototype as unknown as Record<string, unknown>).scrollHeight
  delete (HTMLElement.prototype as unknown as Record<string, unknown>).clientHeight
})

function workspaceValue(onFileOpen: WorkspaceContextValue['onFileOpen']): WorkspaceContextValue {
  return {
    currentSkillId: 'demo',
    navStack: [],
    activeFiles: {},
    activeFileDetails: {},
    splitMode: false,
    onFileOpen,
    openSplitEditor: () => {},
    closeFile: () => {},
    updateFileContent: () => {},
    markFileSaved: () => {},
    setFileInFlight: () => {},
    onSaveConflict: () => {},
    reloadOpenFile: async () => {},
    pushNavSkill: () => {},
    popNavTo: () => {},
  }
}

describe('traceTextOpenRequest (decision 2026-08-14: full view = the normal editor surface)', () => {
  it('builds a read-only virtual document the workspace editor opens like any file', () => {
    expect(traceTextOpenRequest('Rendered prompt', '{"a":1}', 'json')).toEqual({
      path: 'trace/rendered-prompt.json',
      title: 'Rendered prompt',
      content: '{"a":1}',
      language: 'json',
      saveEnabled: false,
    })
  })

  it('falls back to a .txt path for plain text', () => {
    expect(traceTextOpenRequest('Live thinking', 'hmm', 'plaintext').path).toBe('trace/live-thinking.txt')
  })
})

describe('TraceText full-view entry', () => {
  it('opens the full text through workspace onFileOpen — no bespoke dialog', () => {
    mockOverflow()
    const onFileOpen = vi.fn()
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    act(() => {
      root.render(
        <WorkspaceProvider value={workspaceValue(onFileOpen)}>
          <TraceText text="long text" label="Answer" />
        </WorkspaceProvider>,
      )
    })

    const button = container.querySelector('[aria-label="View full Answer"]') as HTMLButtonElement
    expect(button).not.toBeNull()
    act(() => {
      button.click()
    })
    expect(onFileOpen).toHaveBeenCalledWith({
      path: 'trace/answer.txt',
      title: 'Answer',
      content: 'long text',
      language: 'plaintext',
      saveEnabled: false,
    })
    expect(document.querySelector('[role="dialog"]')).toBeNull()

    act(() => {
      root.unmount()
    })
    container.remove()
  })

  it('renders no full-view entry without a workspace context (nowhere to open)', () => {
    const html = renderToStaticMarkup(<TraceText text="orphan" label="Answer" />)
    expect(html).not.toContain('View full')
  })
})
