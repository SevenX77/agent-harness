import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SplitEditor } from './SplitEditor'

// The bottom mini-canvas must be a READ-ONLY projection of GRAPH.md (canvas =
// projection design), never a second editor. This guards that SplitEditor
// renders it in compact mode and wires NO graph-editing handlers, so two
// canvases can never race writes to GRAPH.md off independent snapshots (the
// stale-hash 409 class that a duplicate editor would reintroduce).
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

describe('SplitEditor mini-canvas is a read-only projection', () => {
  beforeEach(() => {
    mocks.graphCanvasProps = null
  })

  it('renders the bottom canvas in compact mode with NO graph-editing handlers', () => {
    const onNodeSelect = vi.fn()

    renderToStaticMarkup(<SplitEditor skillId="s1" onNodeSelect={onNodeSelect} />)

    const props = mocks.graphCanvasProps
    expect(props).not.toBeNull()
    // Read-only projection: compact on, navigation kept...
    expect(props?.compact).toBe(true)
    expect(props?.onNodeSelect).toBe(onNodeSelect)
    // ...and every graph-editing handler absent, so the mini-canvas cannot write
    // GRAPH.md. Removing any of these from SplitEditor would reintroduce the
    // dual-editor race this projection design exists to prevent.
    for (const editingHandler of [
      'onReconnectConnection',
      'onPersistConnection',
      'onDisconnectConnection',
      'onCreatePhase',
      'onPhaseFileSave',
    ]) {
      expect(
        props?.[editingHandler],
        `${editingHandler} must NOT reach the read-only mini-canvas`,
      ).toBeUndefined()
    }
  })
})
