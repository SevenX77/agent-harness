import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { buildEdges, CanvasContextMenuContent, GraphCanvas, SkillNode, type SkillGraphNode } from './GraphCanvas'
import { layoutViewportSignature, nextExpandedSubgraphs, topologyOwnerSkillIdForNode } from './GraphCanvas/GraphCanvas'
import { CycleDetectedError, getAutoLayoutedElements } from '../lib/layout'
import type { Edge, Node } from '@xyflow/react'
import type { SkillDetail } from '@/api/types'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'
import { INPUT_ID, OUTPUT_ID, type GlobalNodeData } from './nodes'

const { reactFlowPropsRef, contextMenuItems } = vi.hoisted(() => ({
  reactFlowPropsRef: { current: null as null | Record<string, unknown> },
  contextMenuItems: [] as Array<{ label: string; onSelect?: () => void }>,
}))

vi.mock('@xyflow/react', () => ({
  Background: () => <div data-testid="background" />,
  Controls: () => <div data-testid="controls" />,
  Handle: () => <span data-testid="handle" />,
  MarkerType: { ArrowClosed: 'arrowclosed' },
  MiniMap: () => <div data-testid="minimap" />,
  Panel: ({ children }: { children: ReactNode }) => <div data-testid="panel">{children}</div>,
  Position: { Left: 'left', Right: 'right', Top: 'top', Bottom: 'bottom' },
  ReactFlow: (props: { children: ReactNode; nodeOrigin?: [number, number] }) => {
    reactFlowPropsRef.current = props
    return <div data-testid="react-flow" data-node-origin={JSON.stringify(props.nodeOrigin)}>{props.children}</div>
  },
  addEdge: vi.fn((edge, edges) => [...edges, edge]),
  reconnectEdge: vi.fn((_oldEdge, newConnection, edges) => [...edges, newConnection]),
  useEdgesState: vi.fn((initialEdges) => [initialEdges, vi.fn(), vi.fn()]),
  useNodesState: vi.fn((initialNodes) => [initialNodes, vi.fn(), vi.fn()]),
  useReactFlow: vi.fn(() => ({
    flowToScreenPosition: (position: { x: number; y: number }) => position,
  })),
  useViewport: vi.fn(() => ({ x: 0, y: 0, zoom: 1 })),
}))

vi.mock('../lib/layout', () => {
  class CycleDetectedError extends Error {
    constructor() {
      super('SKILL contains a cyclic dependency - cannot auto-layout')
      this.name = 'CycleDetectedError'
    }
  }

  return {
    CycleDetectedError,
    getAutoLayoutedElements: vi.fn((nodes, edges) => ({ nodes, edges })),
  }
})

vi.mock('./ui/tooltip', () => ({
  Tooltip: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

vi.mock('@/components/ui/popover', () => ({
  Popover: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  PopoverAnchor: ({ children }: { children: ReactNode }) => <>{children}</>,
  PopoverContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/context-menu', () => ({
  ContextMenu: ({ children }: { children: ReactNode }) => <div data-testid="context-menu">{children}</div>,
  ContextMenuContent: ({ children }: { children: ReactNode }) => <div data-testid="context-menu-content">{children}</div>,
  ContextMenuItem: ({ children, onSelect }: { children: ReactNode; onSelect?: () => void }) => {
    const labelFromNode = (node: ReactNode): string => {
      if (Array.isArray(node)) {
        return node.map(labelFromNode).join('')
      }
      if (typeof node === 'string' || typeof node === 'number') {
        return String(node)
      }
      return ''
    }
    const label = labelFromNode(children)
    contextMenuItems.push({ label, onSelect })
    return <button type="button">{children}</button>
  },
  ContextMenuSeparator: () => <hr />,
  ContextMenuSub: ({ children }: { children: ReactNode }) => <div data-testid="context-menu-sub">{children}</div>,
  ContextMenuSubContent: ({ children }: { children: ReactNode }) => <div data-testid="context-menu-sub-content">{children}</div>,
  ContextMenuSubTrigger: ({ children }: { children: ReactNode }) => <button type="button">{children}</button>,
  ContextMenuTrigger: ({ children }: { children: ReactNode }) => <div data-testid="context-menu-trigger">{children}</div>,
}))

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
  },
}))

const layoutMock = vi.mocked(getAutoLayoutedElements)

function phaseNode(id: string, dependsOn: string[] = [], isOutput = false): SkillGraphNode {
  return {
    id,
    type: 'skill',
    position: { x: 0, y: 0 },
    data: {
      skillId: 'demo',
      label: id,
      mode: 'llm',
      status: 'idle',
      dependsOn,
      isOutput,
    },
  }
}

function globalNode(id: string, type: 'globalInput' | 'globalOutput'): Node<GlobalNodeData, typeof type> {
  return {
    id,
    type,
    position: { x: 0, y: 0 },
    data: {
      type: type === 'globalInput' ? 'global-input' : 'global-output',
      schema: { inputs: [], outputs: [] },
      skillId: 'demo',
    },
  }
}

function skillNodeProps(overrides: Partial<SkillGraphNode['data']> = {}): Parameters<typeof SkillNode>[0] {
  return {
    id: 'phase',
    type: 'skill',
    data: {
      skillId: 'demo',
      label: 'Phase',
      mode: 'llm',
      status: 'idle',
      dependsOn: [],
      ...overrides,
    },
    selected: false,
    isConnectable: true,
    draggable: false,
    selectable: true,
    deletable: false,
    dragging: false,
    zIndex: 0,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
  }
}

function skillNodeHtml(overrides: Partial<SkillGraphNode['data']> = {}): string {
  return renderToStaticMarkup(<SkillNode {...skillNodeProps(overrides)} />)
}

function renderSkillNodeRoot(overrides: Partial<SkillGraphNode['data']> = {}) {
  const node = SkillNode(skillNodeProps(overrides))
  if (!isValidElement(node)) {
    throw new Error('SkillNode did not return an element')
  }
  return node as ReactElement<{
    onDoubleClick?: (event: { stopPropagation: () => void }) => void
  }>
}

function textContent(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(textContent).join('')
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (isValidElement(node)) {
    const props = node.props as { children?: ReactNode }
    return textContent(props.children)
  }
  return ''
}

function findClickableByText(node: ReactNode, text: string): ReactElement<{ onClick?: () => void }> | null {
  if (!isValidElement(node)) return null
  const props = node.props as { children?: ReactNode; onClick?: () => void }
  if (typeof props.onClick === 'function' && textContent(props.children).includes(text)) {
    return node as ReactElement<{ onClick?: () => void }>
  }
  const children = props.children
  if (Array.isArray(children)) {
    for (const child of children) {
      const match = findClickableByText(child, text)
      if (match) return match
    }
    return null
  }
  return findClickableByText(children, text)
}

function edgeIds(nodes: SkillGraphNode[]): string[] {
  return buildEdges(nodes).map((edge) => `${edge.source}->${edge.target}`)
}

function graphSkillDetail(phases: Array<{ id: string; src: string; depends_on: string[] }>): SkillDetail {
  return {
    manifest: {
      schema_version: CURRENT_SCHEMA_VERSION,
      name: 'demo',
      description: 'Demo',
      io: {
        inputs: { type: 'object', properties: {} },
        outputs: { type: 'object', properties: {} },
      },
      phases: phases.map((p) => p.id),
    },
    graph_topology: phases.map((phase) => ({
      ...phase,
      mode: phase.src.endsWith('/SKILL.md') ? 'skill' : phase.src.endsWith('/SUBGRAPH.md') ? 'subgraph' : 'logic',
    })),
    node_schema_v21: {},
    io_schema: {},
    file_paths: {},
    files: {},
    manifest_errors: null,
    has_golden: false,
    latest_run_metadata: null,
    lint_result: null,
  }
}

function expectContextEdges(nodes: SkillGraphNode[]) {
  for (const edge of buildEdges(nodes)) {
    expect(edge.type).toBe('contextEdge')
    expect(edge.markerEnd).toBeUndefined()
    expect(edge.data?.hasTraceData).toBe(false)
    expect(edge.data?.sourcePhaseId).toBe(edge.source)
    expect(edge.data?.targetPhaseId).toBe(edge.target)
  }
}

describe('GraphCanvas', () => {
  beforeEach(() => {
    reactFlowPropsRef.current = null
    contextMenuItems.length = 0
    layoutMock.mockReset()
    layoutMock.mockImplementation((nodes: Node[], edges: Edge[]) => ({ nodes, edges }))
  })

  it('does not render the redundant edit graph title block', () => {
    const html = renderToStaticMarkup(<GraphCanvas skillId="demo-skill" />)

    expect(html).not.toContain('Edit graph')
  })

  it('uses center-origin node positioning so handles align on straight flows', () => {
    const html = renderToStaticMarkup(<GraphCanvas skillId="demo-skill" />)

    expect(html).toContain('data-node-origin="[0.5,0.5]"')
  })

  it('hides the React Flow attribution via the library option', () => {
    renderToStaticMarkup(<GraphCanvas skillId="demo-skill" />)

    const props = reactFlowPropsRef.current as {
      proOptions?: { hideAttribution?: boolean }
    } | null

    expect(props?.proOptions?.hideAttribution).toBe(true)
  })

  it('opens the properties panel when a skill node is clicked', () => {
    const onNodeSelect = vi.fn()
    const onPanelChange = vi.fn()
    const onNodeFileOpen = vi.fn()
    renderToStaticMarkup(
      <GraphCanvas
        skillId="demo-skill"
        onNodeSelect={onNodeSelect}
        onNodeFileOpen={onNodeFileOpen}
        onPanelChange={onPanelChange}
      />,
    )

    const props = reactFlowPropsRef.current as {
      onNodeClick?: (event: unknown, node: SkillGraphNode) => void
    } | null
    const selected = phaseNode('setup')
    props?.onNodeClick?.({}, selected)

    expect(onNodeSelect).toHaveBeenCalledWith({ id: 'setup', data: selected.data })
    expect(onPanelChange).toHaveBeenCalledWith('properties')
    expect(onNodeFileOpen).not.toHaveBeenCalled()
  })

  it('opens graph properties and clears node selection when the empty pane is clicked', () => {
    const onNodeDeselect = vi.fn()
    const onPanelChange = vi.fn()
    const onNodeFileOpen = vi.fn()
    renderToStaticMarkup(
      <GraphCanvas
        skillId="demo-skill"
        selectedNodeId="setup"
        onNodeDeselect={onNodeDeselect}
        onNodeFileOpen={onNodeFileOpen}
        onPanelChange={onPanelChange}
      />,
    )

    const props = reactFlowPropsRef.current as {
      onPaneClick?: () => void
    } | null
    props?.onPaneClick?.()

    expect(onNodeDeselect).toHaveBeenCalled()
    expect(onPanelChange).toHaveBeenCalledWith('properties')
    expect(onNodeFileOpen).not.toHaveBeenCalled()
  })

  it('does not treat a node as still selected after the empty pane was clicked', () => {
    vi.useFakeTimers()
    try {
      const onNodeSelect = vi.fn()
      const onNodeDeselect = vi.fn()
      const onPanelChange = vi.fn()
      const onNodeFileOpen = vi.fn()
      renderToStaticMarkup(
        <GraphCanvas
          skillId="demo-skill"
          selectedNodeId="setup"
          onNodeSelect={onNodeSelect}
          onNodeDeselect={onNodeDeselect}
          onNodeFileOpen={onNodeFileOpen}
          onPanelChange={onPanelChange}
        />,
      )

      const props = reactFlowPropsRef.current as {
        onPaneClick?: () => void
        onNodeClick?: (event: unknown, node: SkillGraphNode) => void
      } | null
      props?.onPaneClick?.()
      onNodeFileOpen.mockClear()
      onPanelChange.mockClear()

      const selected = phaseNode('setup')
      selected.data = {
        ...selected.data,
        mode: 'logic',
        filePath: 'phases/setup/LOGIC.md',
      }
      props?.onNodeClick?.({}, selected)
      vi.advanceTimersByTime(220)

      expect(onNodeDeselect).toHaveBeenCalled()
      expect(onNodeSelect).toHaveBeenCalledWith({ id: 'setup', data: selected.data })
      expect(onPanelChange).toHaveBeenCalledWith('properties')
      expect(onNodeFileOpen).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('opens the I/O panel when a global input or output node is clicked', () => {
    const onNodeSelect = vi.fn()
    const onNodeDeselect = vi.fn()
    const onPanelChange = vi.fn()
    const onNodeFileOpen = vi.fn()
    renderToStaticMarkup(
      <GraphCanvas
        skillId="demo-skill"
        onNodeSelect={onNodeSelect}
        onNodeDeselect={onNodeDeselect}
        onNodeFileOpen={onNodeFileOpen}
        onPanelChange={onPanelChange}
      />,
    )

    const props = reactFlowPropsRef.current as {
      onNodeClick?: (event: unknown, node: Node<GlobalNodeData, 'globalInput' | 'globalOutput'>) => void
    } | null

    props?.onNodeClick?.({}, globalNode(INPUT_ID, 'globalInput'))
    props?.onNodeClick?.({}, globalNode(OUTPUT_ID, 'globalOutput'))

    expect(onPanelChange).toHaveBeenCalledTimes(2)
    expect(onPanelChange).toHaveBeenNthCalledWith(1, 'input')
    expect(onPanelChange).toHaveBeenNthCalledWith(2, 'input')
    expect(onNodeSelect).not.toHaveBeenCalled()
    expect(onNodeDeselect).toHaveBeenCalledTimes(2)
    expect(onNodeFileOpen).not.toHaveBeenCalled()
  })

  it('opens the phase file when an already-selected skill node is clicked again', () => {
    vi.useFakeTimers()
    try {
      const onNodeSelect = vi.fn()
      const onPanelChange = vi.fn()
      const onNodeFileOpen = vi.fn()
      renderToStaticMarkup(
        <GraphCanvas
          skillId="demo-skill"
          selectedNodeId="setup"
          onNodeSelect={onNodeSelect}
          onNodeFileOpen={onNodeFileOpen}
          onPanelChange={onPanelChange}
        />,
      )

      const props = reactFlowPropsRef.current as {
        onNodeClick?: (event: unknown, node: SkillGraphNode) => void
      } | null
      const selected = phaseNode('setup')
      selected.data = {
        ...selected.data,
        mode: 'logic',
        filePath: 'phases/setup/LOGIC.md',
      }
      props?.onNodeClick?.({}, selected)

      expect(onNodeSelect).toHaveBeenCalledWith({ id: 'setup', data: selected.data })
      expect(onPanelChange).not.toHaveBeenCalledWith('properties')
      expect(onNodeFileOpen).not.toHaveBeenCalled()

      vi.advanceTimersByTime(220)

      expect(onNodeFileOpen).toHaveBeenCalledWith({
        path: 'phases/setup/LOGIC.md',
        skillId: 'demo',
        workspaceRoot: null,
        language: 'markdown',
        saveEnabled: true,
      })
    } finally {
      vi.useRealTimers()
    }
  })

  it('opens inline subgraph child files with the child workspace identity, not a parent-prefixed string', () => {
    vi.useFakeTimers()
    try {
      const onNodeFileOpen = vi.fn()
      const childNode: SkillGraphNode = {
        ...phaseNode('__subpreview__::node::event_timeline::review'),
        data: {
          ...phaseNode('review').data,
          skillId: 'event-extraction',
          workspaceRoot: '/repo/skills/story-deconstruction-v3/subgraph/event-timeline/subgraph/event-extraction',
          phaseId: 'review',
          label: 'review',
          mode: 'llm',
          filePath: 'phases/review/SKILL.md',
        },
      }
      renderToStaticMarkup(
        <GraphCanvas
          skillId="story-deconstruction-v3"
          selectedNodeId={childNode.id}
          onNodeFileOpen={onNodeFileOpen}
        />,
      )

      const props = reactFlowPropsRef.current as {
        onNodeClick?: (event: unknown, node: SkillGraphNode) => void
      } | null
      props?.onNodeClick?.({}, childNode)
      vi.advanceTimersByTime(220)

      expect(onNodeFileOpen).toHaveBeenCalledWith({
        path: 'phases/review/SKILL.md',
        skillId: 'event-extraction',
        workspaceRoot: '/repo/skills/story-deconstruction-v3/subgraph/event-timeline/subgraph/event-extraction',
        language: 'markdown',
        saveEnabled: true,
      })
    } finally {
      vi.useRealTimers()
    }
  })

  it('does not open a subgraph file when the second click becomes a drill double-click', () => {
    vi.useFakeTimers()
    try {
      const onNodeFileOpen = vi.fn()
      renderToStaticMarkup(
        <GraphCanvas
          skillId="demo-skill"
          selectedNodeId="child"
          onNodeFileOpen={onNodeFileOpen}
        />,
      )

      const props = reactFlowPropsRef.current as {
        onNodeClick?: (event: unknown, node: SkillGraphNode) => void
        onNodeDoubleClick?: (event: unknown, node: SkillGraphNode) => void
      } | null
      const selected = phaseNode('child')
      selected.data = {
        ...selected.data,
        mode: 'subgraph',
        subgraphPath: '/abs/child',
        filePath: 'phases/child/SUBGRAPH.md',
      }

      props?.onNodeClick?.({}, selected)
      props?.onNodeDoubleClick?.({}, selected)
      vi.advanceTimersByTime(220)

      expect(onNodeFileOpen).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('selects inline subgraph child nodes by their canonical phase id, not canvas namespace id', () => {
    const onNodeSelect = vi.fn()
    renderToStaticMarkup(<GraphCanvas skillId="demo-skill" onNodeSelect={onNodeSelect} />)

    const props = reactFlowPropsRef.current as {
      onNodeClick?: (event: unknown, node: SkillGraphNode) => void
    } | null
    const selected: SkillGraphNode = {
      ...phaseNode('__subpreview__::node::parent::plan'),
      data: {
        ...phaseNode('plan').data,
        skillId: 'child-skill',
        phaseId: 'plan',
        label: 'plan',
      },
    }
    props?.onNodeClick?.({}, selected)

    expect(onNodeSelect).toHaveBeenCalledWith({ id: 'plan', data: selected.data })
  })

  it('renders new phase node actions under an Add Phase Node submenu', () => {
    const onCreatePhase = vi.fn()
    const html = renderToStaticMarkup(<GraphCanvas skillId="demo-skill" onCreatePhase={onCreatePhase} />)

    expect(html).not.toContain('Add phase')
    expect(html).not.toContain('Macro contract')
    expect(html).toContain('Add Phase Node')
    expect(html).toContain('Agent Phase')
    expect(html).toContain('Logic Phase')
    expect(html).toContain('Subgraph Phase')

    contextMenuItems.find((item) => item.label === 'Agent Phase')?.onSelect?.()
    contextMenuItems.find((item) => item.label === 'Logic Phase')?.onSelect?.()
    contextMenuItems.find((item) => item.label === 'Subgraph Phase')?.onSelect?.()

    expect(onCreatePhase).not.toHaveBeenCalled()
  })

  it('keeps viewport controls out of the canvas chrome and exposes them in the context menu', () => {
    const onZoomIn = vi.fn()
    const onZoomOut = vi.fn()
    const onFitView = vi.fn()
    const onToggleCanvasLock = vi.fn()
    const html = renderToStaticMarkup(<GraphCanvas skillId="demo-skill" />)

    expect(html).not.toContain('data-testid="controls"')

    contextMenuItems.length = 0
    renderToStaticMarkup(
      <CanvasContextMenuContent
        edgeMenuConnection={null}
        canvasLocked={false}
        onZoomIn={onZoomIn}
        onZoomOut={onZoomOut}
        onFitView={onFitView}
        onToggleCanvasLock={onToggleCanvasLock}
      />,
    )

    contextMenuItems.find((item) => item.label === 'Zoom in')?.onSelect?.()
    contextMenuItems.find((item) => item.label === 'Zoom out')?.onSelect?.()
    contextMenuItems.find((item) => item.label === 'Fit view')?.onSelect?.()
    contextMenuItems.find((item) => item.label === 'Lock canvas')?.onSelect?.()

    expect(onZoomIn).toHaveBeenCalled()
    expect(onZoomOut).toHaveBeenCalled()
    expect(onFitView).toHaveBeenCalled()
    expect(onToggleCanvasLock).toHaveBeenCalled()
  })

  it('persists valid phase node connections', () => {
    const onPersistConnection = vi.fn()
    renderToStaticMarkup(
      <GraphCanvas
        skillId="demo-skill"
        skillDetail={graphSkillDetail([
          { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
          { id: 'review', src: 'phases/review/LOGIC.md', depends_on: [] },
        ])}
        onPersistConnection={onPersistConnection}
      />,
    )

    const props = reactFlowPropsRef.current as {
      onConnect?: (connection: { source: string; target: string }) => void
    } | null
    props?.onConnect?.({ source: 'draft', target: 'review' })

    expect(onPersistConnection).toHaveBeenCalledWith({ source: 'draft', target: 'review' })
  })

  it('persists explicit graph input and output boundary connections', () => {
    const onPersistConnection = vi.fn()
    renderToStaticMarkup(
      <GraphCanvas
        skillId="demo-skill"
        skillDetail={graphSkillDetail([
          { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
        ])}
        onPersistConnection={onPersistConnection}
      />,
    )

    const props = reactFlowPropsRef.current as {
      onConnect?: (connection: { source: string; target: string }) => void
    } | null
    props?.onConnect?.({ source: INPUT_ID, target: 'draft' })
    props?.onConnect?.({ source: 'draft', target: OUTPUT_ID })

    expect(onPersistConnection).toHaveBeenCalledWith({ source: INPUT_ID, target: 'draft' })
    expect(onPersistConnection).toHaveBeenCalledWith({ source: 'draft', target: OUTPUT_ID })
  })

  it('does not persist invalid phase node connections', () => {
    const onPersistConnection = vi.fn()
    renderToStaticMarkup(
      <GraphCanvas
        skillId="demo-skill"
        skillDetail={graphSkillDetail([
          { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
          { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
        ])}
        onPersistConnection={onPersistConnection}
      />,
    )

    const props = reactFlowPropsRef.current as {
      onConnect?: (connection: { source: string; target: string }) => void
    } | null
    props?.onConnect?.({ source: 'draft', target: 'draft' })
    props?.onConnect?.({ source: 'draft', target: 'review' })
    props?.onConnect?.({ source: 'missing_phase', target: 'review' })
    props?.onConnect?.({ source: 'draft', target: 'missing_phase' })

    expect(onPersistConnection).not.toHaveBeenCalled()
  })

  it('opens an edge context menu action for disconnecting phase dependencies', () => {
    const onDisconnectConnection = vi.fn()
    renderToStaticMarkup(
      <CanvasContextMenuContent
        edgeMenuConnection={{ source: 'draft', target: 'review' }}
        onDisconnectConnection={onDisconnectConnection}
      />,
    )

    contextMenuItems.find((item) => item.label === 'Disconnect')?.onSelect?.()

    expect(onDisconnectConnection).toHaveBeenCalledWith({ source: 'draft', target: 'review' })
  })

  it('opens a destructive node context menu action for deleting phase nodes', () => {
    const onDeletePhase = vi.fn()
    renderToStaticMarkup(
      <CanvasContextMenuContent
        edgeMenuConnection={null}
        nodeMenuPhaseId="draft"
        onDeletePhase={onDeletePhase}
      />,
    )

    contextMenuItems.find((item) => item.label === 'Delete node')?.onSelect?.()

    expect(onDeletePhase).toHaveBeenCalledWith('draft')
  })

  it('enables reconnectable edges on the canvas', () => {
    renderToStaticMarkup(
      <GraphCanvas
        skillId="demo-skill"
        skillDetail={graphSkillDetail([
          { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
          { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
        ])}
      />,
    )

    const props = reactFlowPropsRef.current as { edgesReconnectable?: boolean } | null
    expect(props?.edgesReconnectable).toBe(true)
  })

  it('reconnects an edge through a single atomic onReconnectConnection, not the disconnect-then-persist chain', async () => {
    // n2-canvas #8 lost-update fix: when the single atomic handler is wired, the
    // canvas must route the whole reconnect through it ONCE — never the
    // disconnect().then(persist) chain that issued two serialize round-trips and
    // hit a 409 on the second stale-hash write.
    const onReconnectConnection = vi.fn().mockResolvedValue(undefined)
    const onDisconnectConnection = vi.fn().mockResolvedValue(undefined)
    const onPersistConnection = vi.fn().mockResolvedValue(undefined)
    renderToStaticMarkup(
      <GraphCanvas
        skillId="demo-skill"
        skillDetail={graphSkillDetail([
          { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
          { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
          { id: 'publish', src: 'phases/publish/SKILL.md', depends_on: [] },
        ])}
        onReconnectConnection={onReconnectConnection}
        onDisconnectConnection={onDisconnectConnection}
        onPersistConnection={onPersistConnection}
      />,
    )

    const props = reactFlowPropsRef.current as {
      onReconnect?: (oldEdge: { source: string; target: string }, newConnection: { source: string; target: string }) => void
    } | null
    // Drag the target endpoint of draft→review across to publish.
    props?.onReconnect?.({ source: 'draft', target: 'review' }, { source: 'draft', target: 'publish' })
    await Promise.resolve()
    await Promise.resolve()

    expect(onReconnectConnection).toHaveBeenCalledTimes(1)
    expect(onReconnectConnection).toHaveBeenCalledWith(
      { source: 'draft', target: 'review' },
      { source: 'draft', target: 'publish' },
    )
    // The two-round-trip chain must NOT be used when the atomic handler exists.
    expect(onDisconnectConnection).not.toHaveBeenCalled()
    expect(onPersistConnection).not.toHaveBeenCalled()
  })

  it('reconnects phase edges onto graph Output through the same atomic reconnect path', async () => {
    const onReconnectConnection = vi.fn().mockResolvedValue(undefined)
    renderToStaticMarkup(
      <GraphCanvas
        skillId="demo-skill"
        skillDetail={graphSkillDetail([
          { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
          { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
        ])}
        onReconnectConnection={onReconnectConnection}
      />,
    )

    const props = reactFlowPropsRef.current as {
      onReconnect?: (oldEdge: { source: string; target: string }, newConnection: { source: string; target: string }) => void
    } | null

    props?.onReconnect?.({ source: 'draft', target: 'review' }, { source: 'draft', target: OUTPUT_ID })
    await Promise.resolve()
    await Promise.resolve()

    expect(onReconnectConnection).toHaveBeenCalledWith(
      { source: 'draft', target: 'review' },
      { source: 'draft', target: OUTPUT_ID },
    )
  })

  it('reconnects phase edges onto graph Input through the same atomic reconnect path', async () => {
    const onReconnectConnection = vi.fn().mockResolvedValue(undefined)
    renderToStaticMarkup(
      <GraphCanvas
        skillId="demo-skill"
        skillDetail={graphSkillDetail([
          { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
          { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
        ])}
        onReconnectConnection={onReconnectConnection}
      />,
    )

    const props = reactFlowPropsRef.current as {
      onReconnect?: (oldEdge: { source: string; target: string }, newConnection: { source: string; target: string }) => void
    } | null

    props?.onReconnect?.({ source: 'draft', target: 'review' }, { source: INPUT_ID, target: 'review' })
    await Promise.resolve()
    await Promise.resolve()

    expect(onReconnectConnection).toHaveBeenCalledWith(
      { source: 'draft', target: 'review' },
      { source: INPUT_ID, target: 'review' },
    )
  })

  it('falls back to disconnect-then-persist when no atomic onReconnectConnection is wired', async () => {
    // The compact SplitEditor canvas does not pass onReconnectConnection; the
    // legacy chained path must still function so that surface keeps reconnecting.
    const onDisconnectConnection = vi.fn().mockResolvedValue(undefined)
    const onPersistConnection = vi.fn().mockResolvedValue(undefined)
    renderToStaticMarkup(
      <GraphCanvas
        skillId="demo-skill"
        skillDetail={graphSkillDetail([
          { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
          { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
          { id: 'publish', src: 'phases/publish/SKILL.md', depends_on: [] },
        ])}
        onDisconnectConnection={onDisconnectConnection}
        onPersistConnection={onPersistConnection}
      />,
    )

    const props = reactFlowPropsRef.current as {
      onReconnect?: (oldEdge: { source: string; target: string }, newConnection: { source: string; target: string }) => void
    } | null
    // Drag the target endpoint of draft→review across to publish.
    props?.onReconnect?.({ source: 'draft', target: 'review' }, { source: 'draft', target: 'publish' })
    await Promise.resolve()
    await Promise.resolve()

    expect(onDisconnectConnection).toHaveBeenCalledWith({ source: 'draft', target: 'review' })
    expect(onPersistConnection).toHaveBeenCalledWith({ source: 'draft', target: 'publish' })
  })

  it('disconnects an edge dropped off a handle via onReconnectEnd', () => {
    const onDisconnectConnection = vi.fn().mockResolvedValue(undefined)
    renderToStaticMarkup(
      <GraphCanvas
        skillId="demo-skill"
        skillDetail={graphSkillDetail([
          { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
          { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
        ])}
        onDisconnectConnection={onDisconnectConnection}
      />,
    )

    const props = reactFlowPropsRef.current as {
      onReconnectStart?: () => void
      onReconnectEnd?: (
        event: unknown,
        edge: { id: string; source: string; target: string },
        handleType: 'source' | 'target',
        connectionState: { isValid: boolean | null },
      ) => void
    } | null
    // Start the drag (no landing), then release off any handle (isValid null).
    props?.onReconnectStart?.()
    props?.onReconnectEnd?.({}, { id: 'draft->review', source: 'draft', target: 'review' }, 'target', { isValid: null })

    expect(onDisconnectConnection).toHaveBeenCalledWith({ source: 'draft', target: 'review' })
  })

  it('does not disconnect on onReconnectEnd when the edge landed on a valid handle', () => {
    const onDisconnectConnection = vi.fn().mockResolvedValue(undefined)
    const onPersistConnection = vi.fn().mockResolvedValue(undefined)
    renderToStaticMarkup(
      <GraphCanvas
        skillId="demo-skill"
        skillDetail={graphSkillDetail([
          { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
          { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
          { id: 'publish', src: 'phases/publish/SKILL.md', depends_on: [] },
        ])}
        onDisconnectConnection={onDisconnectConnection}
        onPersistConnection={onPersistConnection}
      />,
    )

    const props = reactFlowPropsRef.current as {
      onReconnectStart?: () => void
      onReconnect?: (oldEdge: { source: string; target: string }, newConnection: { source: string; target: string }) => void
      onReconnectEnd?: (
        event: unknown,
        edge: { id: string; source: string; target: string },
        handleType: 'source' | 'target',
        connectionState: { isValid: boolean | null },
      ) => void
    } | null
    // A successful reconnect fires onReconnect (landed=true) before onReconnectEnd.
    props?.onReconnectStart?.()
    onDisconnectConnection.mockClear()
    props?.onReconnect?.({ source: 'draft', target: 'review' }, { source: 'draft', target: 'publish' })
    props?.onReconnectEnd?.({}, { id: 'draft->review', source: 'draft', target: 'review' }, 'target', { isValid: true })

    // onReconnectEnd must NOT add a second disconnect for the already-moved edge.
    expect(onDisconnectConnection).toHaveBeenCalledTimes(1)
    expect(onDisconnectConnection).toHaveBeenCalledWith({ source: 'draft', target: 'review' })
  })

  it('keeps the loading overlay', () => {
    const html = renderToStaticMarkup(<GraphCanvas skillId="demo-skill" isLoading />)

    expect(html).toContain('Loading graph...')
  })

  it('keeps the initial loading canvas blank and hidden until the first viewport fit is controlled', () => {
    renderToStaticMarkup(<GraphCanvas skillId="demo-skill" isLoading />)

    const props = reactFlowPropsRef.current as {
      nodes?: unknown[]
      fitView?: boolean
      className?: string
    } | null
    expect(props?.nodes).toEqual([])
    expect(props?.fitView).toBeUndefined()
    expect(props?.className).toContain('opacity-0')
    expect(props?.className).toContain('pointer-events-none')
  })

  it('does not treat subgraph expand state as a viewport-refit layout change', () => {
    const collapsed = phaseNode('subgraph')
    collapsed.data.mode = 'subgraph'
    collapsed.data.subgraphPath = '/abs/subgraph'
    collapsed.data.isExpanded = false
    collapsed.data.onToggleSubgraph = () => undefined
    const expanded: SkillGraphNode = {
      ...collapsed,
      data: {
        ...collapsed.data,
        isExpanded: true,
      },
    }

    expect(layoutViewportSignature([collapsed], [])).toBe(layoutViewportSignature([expanded], []))
    expect(layoutViewportSignature([collapsed], [])).not.toBe(layoutViewportSignature([collapsed, phaseNode('next')], []))
  })

  it('keeps inline subgraph topology expansion single-select per canvas level', () => {
    const childA = '__subpreview__::node::segmentation::extract'
    const childB = '__subpreview__::node::segmentation::review'

    expect([...nextExpandedSubgraphs(new Set(), 'segmentation')]).toEqual(['segmentation'])
    expect([...nextExpandedSubgraphs(new Set(['segmentation']), 'event_timeline')]).toEqual(['event_timeline'])
    expect([...nextExpandedSubgraphs(new Set(['event_timeline']), 'event_timeline')]).toEqual([])
    expect([...nextExpandedSubgraphs(new Set(['segmentation']), childA)]).toEqual(['segmentation', childA])
    expect([...nextExpandedSubgraphs(new Set(['segmentation', childA]), childB)]).toEqual(['segmentation', childB])
    expect([...nextExpandedSubgraphs(new Set(['segmentation', childA]), childA)]).toEqual(['segmentation'])
    expect([...nextExpandedSubgraphs(new Set(['segmentation', childA]), 'event_timeline')]).toEqual(['event_timeline'])
  })

  it('keeps nested topology fetches pinned to the root skill boundary', () => {
    const nested = phaseNode('__subpreview__::node::event_timeline::extract')
    nested.data.skillId = 'event-timeline'
    nested.data.workspaceRoot = '/repo/skills/story-deconstruction-v3/subgraph/event-timeline'
    nested.data.subgraphPath = '/repo/skills/story-deconstruction-v3/subgraph/event-timeline/subgraph/event-extraction'

    expect(topologyOwnerSkillIdForNode(nested, 'story-deconstruction-v3')).toBe('story-deconstruction-v3')

    nested.data.topologyOwnerSkillId = 'story-deconstruction-v3'
    expect(topologyOwnerSkillIdForNode(nested, 'other-root')).toBe('story-deconstruction-v3')
  })

  it('keeps the error overlay', () => {
    const html = renderToStaticMarkup(<GraphCanvas skillId="demo-skill" error={new Error('failed')} />)

    expect(html).toContain('Failed to load skill graph.')
  })

  it('keeps rendering the graph when auto-layout detects a cycle', () => {
    layoutMock.mockImplementation(() => {
      throw new CycleDetectedError()
    })

    const html = renderToStaticMarkup(<GraphCanvas skillId="demo-skill" />)

    const props = reactFlowPropsRef.current as {
      nodes?: unknown[]
      edges?: unknown[]
    } | null
    expect(html).not.toContain('SKILL contains cyclic dependency - cannot render graph.')
    expect(props?.nodes?.length).toBeGreaterThan(0)
    expect(props?.edges).toBeDefined()
  })

  it('builds declared serial dependency edges without inferred graph boundaries', () => {
    const nodes = [phaseNode('A'), phaseNode('B', ['A']), phaseNode('C', ['B'])]

    expect(edgeIds(nodes)).toEqual([
      'A->B',
      'B->C',
    ])
    expectContextEdges(nodes)
  })

  it('uses Cancel/Allow actions for sequential overwrite warnings', () => {
    const html = skillNodeHtml({
      activeConflict: {
        nodeId: 'review',
        fieldName: 'events_raw',
        ancestorNodeId: 'aggregate',
      },
      onAllowSequentialOverwrite: () => undefined,
      onCancelSequentialOverwrite: () => undefined,
    })

    expect(html).toContain('Cancel')
    expect(html).toContain('Allow Overwrite')
    expect(html).not.toContain('Deny')
  })

  it('passes the full conflict identity when allowing a sequential overwrite', () => {
    const onAllowSequentialOverwrite = vi.fn()
    const node = renderSkillNodeRoot({
      activeConflict: {
        nodeId: 'review',
        fieldName: 'events_raw',
        ancestorNodeId: 'aggregate',
      },
      onAllowSequentialOverwrite,
      onCancelSequentialOverwrite: () => undefined,
    })

    findClickableByText(node, 'Allow Overwrite')?.props.onClick?.()

    expect(onAllowSequentialOverwrite).toHaveBeenCalledWith('review', 'events_raw', 'aggregate')
  })

  it('builds only declared branching dependency edges', () => {
    const nodes = [
      phaseNode('A'),
      phaseNode('B', ['A']),
      phaseNode('C', ['A']),
      phaseNode('D', ['B', 'C']),
    ]

    expect(edgeIds(nodes)).toEqual([
      'A->B',
      'A->C',
      'B->D',
      'C->D',
    ])
    expectContextEdges(nodes)
  })

  it('does not infer boundary edges for a single node with no dependencies', () => {
    const nodes = [phaseNode('X')]

    expect(edgeIds(nodes)).toEqual([])
    expectContextEdges(nodes)
  })

  it('renders explicit input and output declarations only', () => {
    const nodes = [phaseNode('A', ['input']), phaseNode('B', ['A'], true)]

    expect(edgeIds(nodes)).toEqual([`${INPUT_ID}->A`, 'A->B', `B->${OUTPUT_ID}`])
    expectContextEdges(nodes)
  })

  it('renders no edges for empty phases', () => {
    expect(edgeIds([])).toEqual([])
    expectContextEdges([])
  })

  it('renders subgraph expand icon button when collapsed', () => {
    const html = skillNodeHtml({ subgraphPath: '/abs/subgraph', isExpanded: false, onToggleSubgraph: () => {} })

    expect(html).toContain('aria-label="Expand subgraph"')
    expect(html).toContain('lucide-plus')
  })

  it('renders subgraph collapse icon button when expanded', () => {
    const html = skillNodeHtml({ subgraphPath: '/abs/subgraph', isExpanded: true, onToggleSubgraph: () => {} })

    expect(html).toContain('aria-label="Collapse subgraph"')
    expect(html).toContain('lucide-minus')
  })

  it('renders the expand toggle even for an unresolved subgraph node (so its recovery state can be opened)', () => {
    // Point 3 (PM 2026-06-23): the toggle gate is the wired callback, NOT a
    // resolved absolute path. build-nodes wires onToggleSubgraph for every
    // SUBGRAPH-kind node, so even a non-absolute reference shows the "+".
    const html = skillNodeHtml({ mode: 'subgraph', subgraphPath: 'legacy.registry.child', isExpanded: false, onToggleSubgraph: () => {} })

    expect(html).toContain('aria-label="Expand subgraph"')
  })

  it('does not render the expand toggle when no toggle callback is wired', () => {
    const html = skillNodeHtml({ mode: 'subgraph', subgraphPath: '/abs/child' })

    expect(html).not.toContain('aria-label="Expand subgraph"')
    expect(html).not.toContain('aria-label="Collapse subgraph"')
  })

  it('does not render a subgraph icon button for regular nodes', () => {
    const html = skillNodeHtml()

    expect(html).not.toContain('aria-label="Expand subgraph"')
    expect(html).not.toContain('aria-label="Collapse subgraph"')
  })

  it('renders a compact Toolbox badge when a phase has subagents', () => {
    const html = skillNodeHtml({
      subagents: [
        { name: 'echo_expert', path: 'subskills/echo_expert', description: 'Echo text.' },
        { name: 'score_expert', path: 'subskills/score_expert', description: 'Score text.' },
      ],
    })

    expect(html).toContain('aria-label="2 subagents available"')
    expect(html).toContain('lucide-briefcase')
    expect(html).toContain('2 subagents available')
  })

  it('does not render a Toolbox badge when a phase has no subagents', () => {
    const html = skillNodeHtml({ subagents: [] })

    expect(html).not.toContain('subagents available')
    expect(html).not.toContain('lucide-briefcase')
  })

  it('lets double-click on a subgraph node propagate so ReactFlow can drill in', () => {
    // Regression (2026-06-23): the node must NOT swallow the double-click. Drill-
    // down is routed by ReactFlow's onNodeDoubleClick on the canvas; if SkillNode
    // calls stopPropagation for subgraph nodes, that handler never fires and
    // double-clicking a subgraph node silently fails to drill in. Inline expand is
    // a separate affordance (the explicit Expand-subgraph button), not double-click.
    const stopPropagation = vi.fn()
    const onToggleSubgraph = vi.fn()
    const node = renderSkillNodeRoot({
      subgraphPath: '/abs/subgraph',
      onToggleSubgraph,
    })

    // Either there is no root onDoubleClick at all, or it does not stop the event.
    node.props.onDoubleClick?.({ stopPropagation })

    expect(stopPropagation).not.toHaveBeenCalled()
    expect(onToggleSubgraph).not.toHaveBeenCalled()
  })
})
