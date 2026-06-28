import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SplitEditor } from './SplitEditor'

const mocks = vi.hoisted(() => ({
  internalGraphCanvasRenderCount: 0,
}))

vi.mock('@/components/GraphCanvas', () => ({
  GraphCanvas: () => {
    mocks.internalGraphCanvasRenderCount += 1
    return <div data-testid="internal-graph-canvas" />
  },
}))

vi.mock('./LazyMonacoPanel', () => ({
  LazyMonacoPanel: () => <div data-testid="monaco" />,
}))

vi.mock('./WorkspaceContext', () => ({
  useWorkspaceContext: () => ({
    activeFileDetails: {
      left: { skillId: 's1', path: 'SKILL.md', hash: 'h0', content: '# skill' },
    },
    splitMode: false,
    openSplitEditor: () => {},
    closeFile: () => {},
    updateFileContent: () => {},
    markFileSaved: () => {},
    setFileInFlight: () => {},
    onSaveConflict: () => {},
  }),
}))

describe('SplitEditor canvas slot', () => {
  beforeEach(() => {
    mocks.internalGraphCanvasRenderCount = 0
  })

  it('places the provided canvas instead of creating another GraphCanvas', () => {
    const html = renderToStaticMarkup(
      <SplitEditor canvas={<div data-testid="provided-graph-canvas" />} />,
    )

    expect(html).toContain('data-testid="provided-graph-canvas"')
    expect(html).not.toContain('data-testid="internal-graph-canvas"')
    expect(mocks.internalGraphCanvasRenderCount).toBe(0)
  })
})
