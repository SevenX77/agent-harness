import type { Edge } from '@xyflow/react'
import { describe, expect, it, vi } from 'vitest'
import type { ContextEdgeData } from '@/components/edges/ContextEdge'
import type { GraphCanvasNode, SkillGraphNode } from '@/components/nodes'
import {
  canvasLayoutSignature,
  layoutCanvasHeightForMode,
  mergeLayoutPositions,
  mergeStableLayoutPositions,
  shouldRunInitialViewportFit,
  updateStableLayoutPositionsFromNodeChanges,
} from './canvas-projection'

function skillNode(
  id: string,
  overrides: Partial<SkillGraphNode['data']> = {},
): SkillGraphNode {
  return {
    id,
    type: 'skill',
    position: { x: 0, y: 0 },
    data: {
      skillId: 'demo',
      label: id,
      mode: 'logic',
      status: 'idle',
      dependsOn: [],
      subgraphPath: null,
      isExpanded: false,
      ...overrides,
    },
  } as SkillGraphNode
}

function edge(
  source: string,
  target: string,
  data: Partial<ContextEdgeData> = {},
): Edge<ContextEdgeData> {
  return {
    id: `${source}->${target}`,
    source,
    target,
    type: 'contextEdge',
    data: {
      hasTraceData: false,
      sourcePhaseId: source,
      targetPhaseId: target,
      ...data,
    },
  }
}

describe('canvas projection contracts', () => {
  it('keeps runtime node decoration out of the layout signature', () => {
    const base = [skillNode('draft'), skillNode('review', { dependsOn: ['draft'] })]
    const decorated = [
      skillNode('draft', {
        status: 'running',
        compileErrors: [{ file: null, line: null, field: null, message: 'missing role', severity: 'fatal' }],
        goldenState: 'has-golden',
      }),
      skillNode('review', {
        dependsOn: ['draft'],
        status: 'error',
        errorMessage: 'validator failed',
        isDirtyDownstream: true,
      }),
    ]

    expect(canvasLayoutSignature(base, [edge('draft', 'review')]))
      .toBe(canvasLayoutSignature(decorated, [edge('draft', 'review')]))
  })

  it('keeps trace edge decoration out of the layout signature', () => {
    const nodes = [skillNode('draft'), skillNode('review', { dependsOn: ['draft'] })]

    expect(canvasLayoutSignature(nodes, [edge('draft', 'review')]))
      .toBe(canvasLayoutSignature(nodes, [
        edge('draft', 'review', {
          hasTraceData: true,
          contextJson: { payload: 'large trace payload' },
          onInspectEdge: vi.fn(),
        }),
      ]))
  })

  it('keeps dependency topology edits out of the layout signature', () => {
    const nodes = [skillNode('draft'), skillNode('review', { dependsOn: ['draft'] })]
    const rewiredNodes = [skillNode('draft', { isOutput: true }), skillNode('review', { dependsOn: [] })]

    expect(canvasLayoutSignature(nodes, [edge('draft', 'review')]))
      .toBe(canvasLayoutSignature(nodes, [edge('review', 'draft')]))
    expect(canvasLayoutSignature(nodes, [edge('draft', 'review')]))
      .toBe(canvasLayoutSignature(nodes, [edge('draft', 'review'), edge('review', 'output')]))
    expect(canvasLayoutSignature(nodes, [edge('draft', 'review')]))
      .toBe(canvasLayoutSignature(rewiredNodes, []))
  })

  it('changes the layout signature when the visible node set changes', () => {
    const nodes = [skillNode('draft'), skillNode('review', { dependsOn: ['draft'] })]

    expect(canvasLayoutSignature(nodes, [edge('draft', 'review')]))
      .not.toBe(canvasLayoutSignature([...nodes, skillNode('publish')], [edge('draft', 'review')]))
  })

  it('does not let normal canvas resizes become layout inputs', () => {
    expect(layoutCanvasHeightForMode(900, 0)).toBe(0)
    expect(layoutCanvasHeightForMode(320, 0.2)).toBe(320)
  })

  it('merges layout positions into fresh render nodes without replacing their data', () => {
    const onToggle = vi.fn()
    const renderNodes = [skillNode('draft', { status: 'running', onToggleSubgraph: onToggle })]
    const layoutNodes: GraphCanvasNode[] = [{ ...skillNode('draft'), position: { x: 120, y: 240 } }]

    const [merged] = mergeLayoutPositions(renderNodes, layoutNodes)

    expect(merged.position).toEqual({ x: 120, y: 240 })
    expect(merged.data.status).toBe('running')
    expect(merged.data.onToggleSubgraph).toBe(onToggle)
  })

  it('preserves existing node positions when a fresh layout adds nodes', () => {
    const previousPositions = new Map<string, GraphCanvasNode['position']>([
      ['draft', { x: 100, y: 200 }],
      ['review', { x: 100, y: 360 }],
    ])
    const renderNodes = [skillNode('draft'), skillNode('review'), skillNode('publish')]
    const layoutNodes: GraphCanvasNode[] = [
      { ...skillNode('draft'), position: { x: 400, y: 100 } },
      { ...skillNode('review'), position: { x: 480, y: 240 } },
      { ...skillNode('publish'), position: { x: 520, y: 420 } },
    ]

    const result = mergeStableLayoutPositions(renderNodes, layoutNodes, previousPositions)

    expect(result.nodes.map((node) => [node.id, node.position])).toEqual([
      ['draft', { x: 100, y: 200 }],
      ['review', { x: 100, y: 360 }],
      ['publish', { x: 520, y: 420 }],
    ])
    expect([...result.positions.keys()]).toEqual(['draft', 'review', 'publish'])
  })

  it('records user node drag positions into the stable layout cache', () => {
    const positions = updateStableLayoutPositionsFromNodeChanges(
      new Map<string, GraphCanvasNode['position']>([
        ['draft', { x: 100, y: 200 }],
        ['review', { x: 100, y: 360 }],
      ]),
      [
        { type: 'position', id: 'draft', position: { x: 180, y: 260 } },
        { type: 'select', id: 'review', selected: true },
        { type: 'remove', id: 'review' },
      ],
    )

    expect([...positions.entries()]).toEqual([
      ['draft', { x: 180, y: 260 }],
    ])
  })

  it('allows exactly the first real mounted layout to fit the viewport', () => {
    expect(shouldRunInitialViewportFit({
      hasLayoutNodes: true,
      hasFitView: true,
      initialFitStarted: false,
      viewportReady: false,
    })).toBe(true)
    expect(shouldRunInitialViewportFit({
      hasLayoutNodes: false,
      hasFitView: true,
      initialFitStarted: false,
      viewportReady: false,
    })).toBe(false)
    expect(shouldRunInitialViewportFit({
      hasLayoutNodes: true,
      hasFitView: false,
      initialFitStarted: false,
      viewportReady: false,
    })).toBe(false)
    expect(shouldRunInitialViewportFit({
      hasLayoutNodes: true,
      hasFitView: true,
      initialFitStarted: true,
      viewportReady: false,
    })).toBe(false)
    expect(shouldRunInitialViewportFit({
      hasLayoutNodes: true,
      hasFitView: true,
      initialFitStarted: false,
      viewportReady: true,
    })).toBe(false)
  })
})
