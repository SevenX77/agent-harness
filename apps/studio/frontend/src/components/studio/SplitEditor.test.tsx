import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SplitEditor } from './SplitEditor'

// The bottom mini-canvas is a second GraphCanvas consumer. The atomic
// reconnect handler lived only on the main canvas; this suite guards the
// thread-through so the compact canvas never silently falls back to the
// legacy disconnect-then-persist chain (the 409 lost-update path).
const mocks = vi.hoisted(() => ({
  graphCanvasProps: null as null | {
    compact?: boolean
    onReconnectConnection?: unknown
    onPersistConnection?: unknown
    onDisconnectConnection?: unknown
  },
}))

vi.mock('@/components/GraphCanvas', () => ({
  GraphCanvas: (props: {
    compact?: boolean
    onReconnectConnection?: unknown
    onPersistConnection?: unknown
    onDisconnectConnection?: unknown
  }) => {
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

describe('SplitEditor compact canvas wiring', () => {
  beforeEach(() => {
    mocks.graphCanvasProps = null
  })

  it('threads the atomic onReconnectConnection handler into the bottom mini-canvas', () => {
    const onReconnectConnection = vi.fn()
    const onPersistConnection = vi.fn()
    const onDisconnectConnection = vi.fn()

    renderToStaticMarkup(
      <SplitEditor
        skillId="s1"
        onReconnectConnection={onReconnectConnection}
        onPersistConnection={onPersistConnection}
        onDisconnectConnection={onDisconnectConnection}
      />,
    )

    expect(mocks.graphCanvasProps).not.toBeNull()
    expect(mocks.graphCanvasProps?.compact).toBe(true)
    // Regression guard: the compact canvas MUST receive the single-serialize
    // atomic handler. Without it, GraphCanvas' onReconnect falls back to
    // onDisconnectConnection().then(onPersistConnection) — two serialize
    // round-trips that 409 on a stale expected_hash and leave GRAPH.md
    // half-mutated.
    expect(mocks.graphCanvasProps?.onReconnectConnection).toBe(onReconnectConnection)
  })
})
