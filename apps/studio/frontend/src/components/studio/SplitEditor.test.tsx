import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SplitEditor } from './SplitEditor'

// Opening a file editor must only squeeze the same canvas into the bottom area.
// It must not swap in a compact/read-only projection with different authoring
// behaviour.
const mocks = vi.hoisted(() => ({
  graphCanvasProps: null as null | Record<string, unknown>,
}))

vi.mock('@/components/GraphCanvas', () => ({
  GraphCanvas: (props: Record<string, unknown>) => {
    mocks.graphCanvasProps = props
    return <div data-testid="graph-canvas" />
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

describe('SplitEditor bottom canvas keeps normal canvas behaviour', () => {
  beforeEach(() => {
    mocks.graphCanvasProps = null
  })

  it('renders the bottom canvas with the same graph-editing handlers', () => {
    const onNodeSelect = vi.fn()
    const onCreatePhase = vi.fn()
    const onDeletePhase = vi.fn()
    const onPersistConnection = vi.fn()
    const onDisconnectConnection = vi.fn()
    const onReconnectConnection = vi.fn()
    const onPhaseFileSave = vi.fn()
    const onNodeFileOpen = vi.fn()

    renderToStaticMarkup(
      <SplitEditor
        skillId="s1"
        onNodeSelect={onNodeSelect}
        onNodeFileOpen={onNodeFileOpen}
        onCreatePhase={onCreatePhase}
        onDeletePhase={onDeletePhase}
        onPersistConnection={onPersistConnection}
        onDisconnectConnection={onDisconnectConnection}
        onReconnectConnection={onReconnectConnection}
        onPhaseFileSave={onPhaseFileSave}
      />,
    )

    const props = mocks.graphCanvasProps
    expect(props).not.toBeNull()
    expect(props?.compact).toBeUndefined()
    expect(props?.onNodeSelect).toBe(onNodeSelect)
    expect(props?.onNodeFileOpen).toBe(onNodeFileOpen)
    expect(props?.onCreatePhase).toBe(onCreatePhase)
    expect(props?.onDeletePhase).toBe(onDeletePhase)
    expect(props?.onPersistConnection).toBe(onPersistConnection)
    expect(props?.onDisconnectConnection).toBe(onDisconnectConnection)
    expect(props?.onReconnectConnection).toBe(onReconnectConnection)
    expect(props?.onPhaseFileSave).toBe(onPhaseFileSave)
  })
})
