import '@xyflow/react/dist/style.css'

import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
} from '@xyflow/react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import type { SkillDetail } from '@/api/types'
import { CycleDetectedError, getAutoLayoutedElements } from '@/lib/layout'
import { ContextEdge, type ContextEdgeData } from '@/components/edges/ContextEdge'
import { GlobalInputNode, GlobalOutputNode } from '@/components/nodes/GlobalInputOutputNode'
import { buildEdges, SkillNode, type GraphCanvasNode, type SkillGraphNode, type SkillGraphNodeData, type SkillNodeStatus } from '@/components/nodes'
import { useOptionalWorkspaceContext } from '@/components/studio/WorkspaceContext'
import type { PanelKind } from '@/components/studio/Toolbar'
import { buildNodes, phaseKindFile } from './build-nodes'

interface GraphCanvasProps {
  skillId: string
  skillDetail?: SkillDetail
  isLoading?: boolean
  error?: unknown
  selectedNodeId?: string | null
  onNodeSelect?: (node: { id: string, data: SkillGraphNodeData }) => void
  onPanelChange?: (panel: PanelKind | null) => void
  statusByNodeId?: Record<string, SkillNodeStatus>
  compact?: boolean
}

const nodeTypes = {
  skill: SkillNode,
  globalInput: GlobalInputNode,
  globalOutput: GlobalOutputNode,
}

const edgeTypes = {
  contextEdge: ContextEdge,
}

export function GraphCanvas({
  skillId,
  skillDetail,
  isLoading = false,
  error,
  selectedNodeId,
  onNodeSelect,
  onPanelChange,
  statusByNodeId,
  compact = false,
}: GraphCanvasProps) {
  const workspace = useOptionalWorkspaceContext()
  const [expandedSubgraphs, setExpandedSubgraphs] = useState<Set<string>>(() => new Set())
  const [selectedCanvasNodeId, setSelectedCanvasNodeId] = useState<string | null>(null)
  const [canvasHeight, setCanvasHeight] = useState(0)
  const canvasRef = useRef<HTMLElement | null>(null)
  const fitViewRef = useRef<(() => void) | null>(null)
  const fitLayout = useCallback(() => {
    window.requestAnimationFrame(() => {
      fitViewRef.current?.()
    })
  }, [])
  const toggleSubgraph = useCallback((nodeId: string) => {
    setExpandedSubgraphs((current) => {
      const next = new Set(current)
      if (next.has(nodeId)) {
        next.delete(nodeId)
      } else {
        next.add(nodeId)
      }
      return next
    })
  }, [])
  const safeStatusByNodeId = useMemo(() => statusByNodeId ?? {}, [statusByNodeId])
  const compactRatio = compact && canvasHeight > 0 && canvasHeight < 500 ? 0.2 : 0

  useEffect(() => {
    const element = canvasRef.current
    if (!element) return
    const updateHeight = () => setCanvasHeight(element.getBoundingClientRect().height)
    updateHeight()
    const observer = new ResizeObserver(updateHeight)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const rawNodes = useMemo(
    () => buildNodes(skillId, skillDetail, expandedSubgraphs, toggleSubgraph, safeStatusByNodeId),
    [expandedSubgraphs, safeStatusByNodeId, skillDetail, skillId, toggleSubgraph],
  )
  const phaseNodes = useMemo(
    () => rawNodes.filter((node): node is SkillGraphNode => node.type === 'skill'),
    [rawNodes],
  )
  const rawEdges = useMemo(() => buildEdges(phaseNodes), [phaseNodes])
  const layoutResult = useMemo((): { nodes: GraphCanvasNode[]; edges: Edge<ContextEdgeData>[]; error: CycleDetectedError | null } => {
    try {
      return { ...getAutoLayoutedElements(rawNodes, rawEdges, { canvasHeight, compactRatio }), error: null }
    } catch (layoutError) {
      if (layoutError instanceof CycleDetectedError) {
        return { nodes: [], edges: [], error: layoutError }
      }
      throw layoutError
    }
  }, [canvasHeight, compactRatio, rawEdges, rawNodes])
  const [nodes, setNodes, onNodesChange] = useNodesState<GraphCanvasNode>(layoutResult.nodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutResult.edges)

  useEffect(() => {
    setNodes(layoutResult.nodes)
    setEdges(layoutResult.edges)
    if (!layoutResult.error) {
      fitLayout()
    }
  }, [fitLayout, layoutResult, setEdges, setNodes])

  useEffect(() => {
    if (layoutResult.error) {
      toast.error('SKILL contains cyclic dependency - cannot render graph')
      console.error(layoutResult.error)
    }
  }, [layoutResult.error])

  const selectedNodes = useMemo(
    () => nodes.map((node) => ({ ...node, selected: node.id === (selectedCanvasNodeId ?? selectedNodeId) })),
    [nodes, selectedCanvasNodeId, selectedNodeId],
  )

  const onConnect = useCallback((connection: Connection) => {
    setEdges((current) => addEdge({ ...connection, type: 'contextEdge' }, current))
    if (connection.source && connection.target) {
      setNodes((current) => current.map((node) => {
        if (node.type !== 'skill' || node.id !== connection.target || node.data.dependsOn.includes(connection.source ?? '')) {
          return node
        }
        return {
          ...node,
          data: {
            ...node.data,
            dependsOn: [...node.data.dependsOn, connection.source],
          },
        }
      }))
    }
  }, [setEdges, setNodes])

  return (
    <section ref={canvasRef} className="relative h-full min-h-0 bg-background">
      {error ? (
        <div className="absolute inset-0 z-10 grid place-items-center bg-background/80 p-8">
          <div className="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            Failed to load skill graph.
          </div>
        </div>
      ) : null}

      {isLoading ? (
        <div className="absolute right-4 top-4 z-10 rounded-md border border-border bg-card px-3 py-2 text-xs text-muted-foreground shadow-sm">
          Loading graph...
        </div>
      ) : null}

      {layoutResult.error ? (
        <div className="absolute inset-0 z-10 grid place-items-center bg-background/80 p-8">
          <div className="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            SKILL contains cyclic dependency - cannot render graph.
          </div>
        </div>
      ) : null}

      <ReactFlow
        nodes={selectedNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={(_, node) => {
          setSelectedCanvasNodeId(node.id)
          if (node.type === 'skill') {
            onNodeSelect?.({ id: node.id, data: node.data })
          }
        }}
        onNodeDragStart={(_, node) => {
          setSelectedCanvasNodeId(node.id)
          if (node.type === 'skill') {
            onNodeSelect?.({ id: node.id, data: node.data })
          }
        }}
        selectNodesOnDrag
        onNodeDoubleClick={(_, node) => {
          setSelectedCanvasNodeId(node.id)
          if (node.type === 'globalInput' || node.type === 'globalOutput') {
            const filePath = node.type === 'globalInput' ? 'io/inputs.json' : 'io/outputs.json'
            workspace?.onFileOpen(`${skillId}/${filePath}`)
            onPanelChange?.('input')
            return
          }
          if (node.type === 'skill') {
            onNodeSelect?.({ id: node.id, data: node.data })
            workspace?.onFileOpen(`${skillId}/${node.data.filePath ?? `phases/${node.id}/${phaseKindFile(node.data)}`}`)
            onPanelChange?.('properties')
          }
        }}
        onInit={(instance) => {
          fitViewRef.current = () => instance.fitView({ padding: 0.2 })
          fitLayout()
        }}
        fitView
        minZoom={0.35}
        maxZoom={1.4}
      >
        <Background gap={18} size={1} />
        <Controls position="bottom-left" />
        {!compact ? <MiniMap pannable zoomable position="bottom-right" style={{ height: 120, width: 200 }} /> : null}
      </ReactFlow>
    </section>
  )
}
