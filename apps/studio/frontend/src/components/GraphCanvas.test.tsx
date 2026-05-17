import React from 'react'
import { renderToString } from 'react-dom/server'
import type { Node } from 'reactflow'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { StudioNodeData } from '../CustomNodes'
import { GraphCanvas } from './GraphCanvas'

vi.mock('reactflow', () => ({
  Background: () => null,
  Controls: () => null,
  Handle: () => null,
  MarkerType: { ArrowClosed: 'arrowclosed' },
  MiniMap: () => null,
  Panel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Position: { Bottom: 'bottom', Top: 'top' },
  ReactFlow: ({
    children,
    nodes,
    onNodeDoubleClick,
  }: {
    children: React.ReactNode
    nodes: Node<StudioNodeData>[]
    onNodeDoubleClick?: (event: unknown, node: Node<StudioNodeData>) => void
  }) => {
    const target = nodes.find((node) => node.id === 'prepare')
    if (target) {
      onNodeDoubleClick?.({}, target)
    }
    return <div>{children}</div>
  },
}))

describe('GraphCanvas', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('dispatches canvas:open-phase-file when an agent node is double-clicked', () => {
    const dispatchEvent = vi.fn()
    const onPhaseDoubleClick = vi.fn()
    vi.stubGlobal('window', { dispatchEvent })

    renderToString(
      <GraphCanvas
        currentSkillName="Root Skill"
        breadcrumbs={[{ skillId: 'root-skill', skillName: 'Root Skill' }]}
        skillDetailError={null}
        nodes={[{
          id: 'prepare',
          type: 'agent',
          data: { label: 'prepare', mode: 'logic', src: 'phases/prepare' },
          position: { x: 0, y: 0 },
        }]}
        edges={[]}
        isDarkMode={false}
        isReadOnly
        onNodesChange={() => undefined}
        onEdgesChange={() => undefined}
        onConnect={() => undefined}
        onResetLayout={() => undefined}
        onBreadcrumbClick={() => undefined}
        onBackToParent={() => undefined}
        onPhaseDoubleClick={onPhaseDoubleClick}
      />,
    )

    expect(onPhaseDoubleClick).not.toHaveBeenCalled()
    expect(dispatchEvent).toHaveBeenCalledOnce()
    const event = dispatchEvent.mock.calls[0]?.[0] as CustomEvent
    expect(event).toBeInstanceOf(CustomEvent)
    expect(event.type).toBe('canvas:open-phase-file')
    expect(event.bubbles).toBe(true)
    expect(event.cancelable).toBe(true)
    expect(event.detail).toEqual({
      skill_id: 'root-skill',
      phase_id: 'prepare',
      file: 'phases/prepare/LOGIC.md',
      readonly: true,
    })
  })
})
