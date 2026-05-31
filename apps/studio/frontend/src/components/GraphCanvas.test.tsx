import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { buildEdges, CanvasContextMenuContent, GraphCanvas, SkillNode, type SkillGraphNode } from './GraphCanvas'
import { CycleDetectedError, getAutoLayoutedElements } from '../lib/layout'
import type { Edge, Node } from '@xyflow/react'
import type { SkillDetail } from '@/api/types'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'

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
  Position: { Left: 'left', Right: 'right', Top: 'top', Bottom: 'bottom' },
  ReactFlow: (props: { children: ReactNode; nodeOrigin?: [number, number] }) => {
    reactFlowPropsRef.current = props
    return <div data-testid="react-flow" data-node-origin={JSON.stringify(props.nodeOrigin)}>{props.children}</div>
  },
  addEdge: vi.fn((edge, edges) => [...edges, edge]),
  useEdgesState: vi.fn((initialEdges) => [initialEdges, vi.fn(), vi.fn()]),
  useNodesState: vi.fn((initialNodes) => [initialNodes, vi.fn(), vi.fn()]),
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

vi.mock('@/components/ui/context-menu', () => ({
  ContextMenu: ({ children }: { children: ReactNode }) => <div data-testid="context-menu">{children}</div>,
  ContextMenuContent: ({ children }: { children: ReactNode }) => <div data-testid="context-menu-content">{children}</div>,
  ContextMenuItem: ({ children, onSelect }: { children: ReactNode; onSelect?: () => void }) => {
    const label = String(children)
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

function phaseNode(id: string, dependsOn: string[] = []): SkillGraphNode {
  return {
    id,
    type: 'skill',
    position: { x: 0, y: 0 },
    data: {
      label: id,
      mode: 'llm',
      status: 'idle',
      dependsOn,
    },
  }
}

function skillNodeProps(overrides: Partial<SkillGraphNode['data']> = {}): Parameters<typeof SkillNode>[0] {
  return {
    id: 'phase',
    type: 'skill',
    data: {
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

  it('opens the properties panel when a skill node is clicked', () => {
    const onNodeSelect = vi.fn()
    const onPanelChange = vi.fn()
    renderToStaticMarkup(<GraphCanvas skillId="demo-skill" onNodeSelect={onNodeSelect} onPanelChange={onPanelChange} />)

    const props = reactFlowPropsRef.current as {
      onNodeClick?: (event: unknown, node: SkillGraphNode) => void
    } | null
    const selected = phaseNode('setup')
    props?.onNodeClick?.({}, selected)

    expect(onNodeSelect).toHaveBeenCalledWith({ id: 'setup', data: selected.data })
    expect(onPanelChange).toHaveBeenCalledWith('properties')
  })

  it('renders new phase node actions under an Add Phase Node submenu', () => {
    const onCreatePhase = vi.fn()
    const html = renderToStaticMarkup(<GraphCanvas skillId="demo-skill" onCreatePhase={onCreatePhase} />)

    expect(html).toContain('Add Phase Node')
    expect(html).toContain('Agent Phase')
    expect(html).toContain('Logic Phase')
    expect(html).toContain('Subgraph Phase')

    contextMenuItems.find((item) => item.label === 'Agent Phase')?.onSelect?.()
    contextMenuItems.find((item) => item.label === 'Logic Phase')?.onSelect?.()
    contextMenuItems.find((item) => item.label === 'Subgraph Phase')?.onSelect?.()

    expect(onCreatePhase).toHaveBeenNthCalledWith(1, 'skill')
    expect(onCreatePhase).toHaveBeenNthCalledWith(2, 'logic')
    expect(onCreatePhase).toHaveBeenNthCalledWith(3, 'subgraph')
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
    props?.onConnect?.({ source: '__global_input__', target: 'review' })
    props?.onConnect?.({ source: 'draft', target: '__global_output__' })

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

  it('keeps the loading overlay', () => {
    const html = renderToStaticMarkup(<GraphCanvas skillId="demo-skill" isLoading />)

    expect(html).toContain('Loading graph...')
  })

  it('keeps the error overlay', () => {
    const html = renderToStaticMarkup(<GraphCanvas skillId="demo-skill" error={new Error('failed')} />)

    expect(html).toContain('Failed to load skill graph.')
  })

  it('keeps the cycle warning overlay', () => {
    layoutMock.mockImplementation(() => {
      throw new CycleDetectedError()
    })

    const html = renderToStaticMarkup(<GraphCanvas skillId="demo-skill" />)

    expect(html).toContain('SKILL contains cyclic dependency - cannot render graph.')
  })

  it('builds serial edges through global input and output', () => {
    const nodes = [phaseNode('A'), phaseNode('B', ['A']), phaseNode('C', ['B'])]

    expect(edgeIds(nodes)).toEqual([
      '__global_input__->A',
      'A->B',
      'B->C',
      'C->__global_output__',
    ])
    expectContextEdges(nodes)
  })

  it('builds branching edges through global input and output', () => {
    const nodes = [
      phaseNode('A'),
      phaseNode('B', ['A']),
      phaseNode('C', ['A']),
      phaseNode('D', ['B', 'C']),
    ]

    expect(edgeIds(nodes)).toEqual([
      '__global_input__->A',
      'A->B',
      'A->C',
      'B->D',
      'C->D',
      'D->__global_output__',
    ])
    expectContextEdges(nodes)
  })

  it('builds single-node edges through global input and output', () => {
    const nodes = [phaseNode('X')]

    expect(edgeIds(nodes)).toEqual([
      '__global_input__->X',
      'X->__global_output__',
    ])
    expectContextEdges(nodes)
  })

  it('builds a direct global input to output edge for empty phases', () => {
    expect(edgeIds([])).toEqual(['__global_input__->__global_output__'])
    expectContextEdges([])
  })

  it('renders subgraph expand icon button when collapsed', () => {
    const html = skillNodeHtml({ subgraphPath: 'subgraph.SKILL.md', isExpanded: false })

    expect(html).toContain('aria-label="Expand subgraph"')
    expect(html).toContain('lucide-plus')
  })

  it('renders subgraph collapse icon button when expanded', () => {
    const html = skillNodeHtml({ subgraphPath: 'subgraph.SKILL.md', isExpanded: true })

    expect(html).toContain('aria-label="Collapse subgraph"')
    expect(html).toContain('lucide-minus')
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

  it('does not propagate double-click on subgraph nodes', () => {
    const stopPropagation = vi.fn()
    const onToggleSubgraph = vi.fn()
    const node = renderSkillNodeRoot({
      subgraphPath: 'subgraph.SKILL.md',
      onToggleSubgraph,
    })

    node.props.onDoubleClick?.({ stopPropagation })

    expect(stopPropagation).toHaveBeenCalledOnce()
    expect(onToggleSubgraph).not.toHaveBeenCalled()
  })
})
