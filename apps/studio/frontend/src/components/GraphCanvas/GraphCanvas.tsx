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
  type ReactFlowInstance,
} from '@xyflow/react'
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { toast } from 'sonner'
import type { SkillDetail } from '@/api/types'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
import { CycleDetectedError, getAutoLayoutedElements } from '@/lib/layout'
import { ContextEdge, type ContextEdgeData } from '@/components/edges/ContextEdge'
import { GlobalInputNode, GlobalOutputNode } from '@/components/nodes/GlobalInputOutputNode'
import { buildEdges, INPUT_ID, OUTPUT_ID, SkillNode, type GraphCanvasNode, type SkillGraphNode, type SkillGraphNodeData, type SkillNodeStatus } from '@/components/nodes'
import { useOptionalWorkspaceContext } from '@/components/studio/WorkspaceContext'
import type { PanelKind } from '@/components/studio/Toolbar'
import { buildNodes, phaseKindFile } from './build-nodes'
import {
  type NewPhaseKind,
  checkSequentialOverwrites,
  addSequentialOverwriteField,
  phaseRefsFromSkillDetail,
  phaseFilePath,
  type OverwriteConflict,
} from './canvas-authoring'

interface GraphCanvasProps {
  skillId: string
  skillDetail?: SkillDetail
  isLoading?: boolean
  error?: unknown
  selectedNodeId?: string | null
  onNodeSelect?: (node: { id: string, data: SkillGraphNodeData }) => void
  onPanelChange?: (panel: PanelKind | null) => void
  onCreatePhase?: (kind: NewPhaseKind) => Promise<void> | void
  onPersistConnection?: (connection: Connection) => Promise<void> | void
  onDisconnectConnection?: (connection: { source: string; target: string }) => Promise<void> | void
  statusByNodeId?: Record<string, SkillNodeStatus>
  compact?: boolean
  onPhaseFileSave?: (args: { path: string; content: string; expectedHash: string }) => Promise<void> | void
}

const nodeTypes = {
  skill: SkillNode,
  globalInput: GlobalInputNode,
  globalOutput: GlobalOutputNode,
}

const edgeTypes = {
  contextEdge: ContextEdge,
}

const CENTER_NODE_ORIGIN: [number, number] = [0.5, 0.5]

function isEdgeContextTarget(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest(
    '.react-flow__edge, .react-flow__edgelabel-renderer, [data-edge-context-target="true"]',
  ))
}

export function GraphCanvas({
  skillId,
  skillDetail,
  isLoading = false,
  error,
  selectedNodeId,
  onNodeSelect,
  onPanelChange,
  onCreatePhase,
  onPersistConnection,
  onDisconnectConnection,
  statusByNodeId,
  compact = false,
  onPhaseFileSave,
}: GraphCanvasProps) {
  const workspace = useOptionalWorkspaceContext()
  const [expandedSubgraphs, setExpandedSubgraphs] = useState<Set<string>>(() => new Set())
  const [selectedCanvasNodeId, setSelectedCanvasNodeId] = useState<string | null>(null)
  const [edgeMenuConnection, setEdgeMenuConnection] = useState<{ source: string; target: string } | null>(null)
  const [canvasHeight, setCanvasHeight] = useState(0)
  const canvasRef = useRef<HTMLElement | null>(null)

  const [warningQueue, setWarningQueue] = useState<OverwriteConflict[]>([])
  const [activeWarningIndex, setActiveWarningIndex] = useState<number>(-1)
  const [cancelledNodeIds, setCancelledNodeIds] = useState<Set<string>>(() => new Set())
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance<GraphCanvasNode & { selected: boolean }, Edge<ContextEdgeData>> | null>(null)

  // 1. Conflict detection effect
  useEffect(() => {
    if (!skillDetail) {
      setWarningQueue([])
      setActiveWarningIndex(-1)
      return
    }
    const phases = phaseRefsFromSkillDetail(skillDetail)
    const conflicts = checkSequentialOverwrites(skillDetail, phases)
    setWarningQueue(conflicts)
    if (conflicts.length > 0) {
      setActiveWarningIndex(0)
    } else {
      setActiveWarningIndex(-1)
    }
  }, [skillDetail])

  // 2. Viewport pan transition effect
  useEffect(() => {
    const activeWarning = warningQueue[activeWarningIndex]
    if (activeWarning && reactFlowInstance) {
      reactFlowInstance.fitView({
        nodes: [{ id: activeWarning.nodeId }],
        duration: 600,
        padding: 0.8,
      })
    }
  }, [activeWarningIndex, warningQueue, reactFlowInstance])

  // 3. Sequential overwrite allow/cancel callbacks
  const handleAllowSequentialOverwrite = useCallback(async (nodeId: string, fieldName: string) => {
    if (!skillDetail || !onPhaseFileSave) return
    const phase = phaseRefsFromSkillDetail(skillDetail).find((p) => p.id === nodeId)
    if (!phase) return
    const relativePath = phaseFilePath(nodeId, phase.mode)
    const currentContent = skillDetail.files?.[relativePath]
    if (!currentContent) return

    const updatedContent = addSequentialOverwriteField(currentContent, fieldName)
    try {
      const sha256Hex = async (text: string) => {
        const msgUint8 = new TextEncoder().encode(text)
        const hashBuffer = await crypto.subtle.digest('SHA-256', msgUint8)
        const hashArray = Array.from(new Uint8Array(hashBuffer))
        return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('')
      }
      const hash = await sha256Hex(currentContent)
      await onPhaseFileSave({
        path: relativePath,
        content: updatedContent,
        expectedHash: hash,
      })
      // Advance warning queue index or clear queue
      if (activeWarningIndex < warningQueue.length - 1) {
        setActiveWarningIndex((prev) => prev + 1)
      } else {
        setWarningQueue([])
        setActiveWarningIndex(-1)
      }
    } catch (saveError) {
      toast.error('Could not whitelist sequential overwrite: ' + (saveError instanceof Error ? saveError.message : String(saveError)))
    }
  }, [skillDetail, onPhaseFileSave, activeWarningIndex, warningQueue])

  const handleCancelWarning = useCallback((nodeId: string) => {
    setCancelledNodeIds((prev) => {
      const next = new Set(prev)
      next.add(nodeId)
      return next
    })
    setWarningQueue([])
    setActiveWarningIndex(-1)
    toast.error('Warning cancelled. Conflict node marked red.')
  }, [])
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

  // Controlled effect to sync activeConflict, isConflictCancelled, and callbacks into the nodes state
  useEffect(() => {
    setNodes((currentNodes) => {
      let changed = false
      const nextNodes = currentNodes.map((node) => {
        if (node.type !== 'skill') return node

        const activeConflict = warningQueue[activeWarningIndex]
        const hasConflict = activeConflict && activeConflict.nodeId === node.id ? activeConflict : undefined
        const isConflictCancelled = cancelledNodeIds.has(node.id)

        // Compare values to prevent unnecessary updates and keep references stable
        if (
          node.data.activeConflict === hasConflict &&
          node.data.isConflictCancelled === isConflictCancelled &&
          node.data.onAllowSequentialOverwrite === handleAllowSequentialOverwrite &&
          node.data.onCancelWarning === handleCancelWarning
        ) {
          return node
        }

        changed = true
        return {
          ...node,
          data: {
            ...node.data,
            activeConflict: hasConflict,
            isConflictCancelled,
            onAllowSequentialOverwrite: handleAllowSequentialOverwrite,
            onCancelWarning: handleCancelWarning,
          },
        }
      })
      return changed ? nextNodes : currentNodes
    })
  }, [warningQueue, activeWarningIndex, cancelledNodeIds, handleAllowSequentialOverwrite, handleCancelWarning, setNodes])

  const selectedNodes = useMemo(
    () => nodes.map((node) => ({ ...node, selected: node.id === (selectedCanvasNodeId ?? selectedNodeId) })),
    [nodes, selectedCanvasNodeId, selectedNodeId],
  )
  const openEdgeContextMenu = useCallback((
    _event: MouseEvent,
    connection: { source: string; target: string },
  ) => {
    if (
      connection.source === INPUT_ID
      || connection.source === OUTPUT_ID
      || connection.target === INPUT_ID
      || connection.target === OUTPUT_ID
    ) {
      setEdgeMenuConnection(null)
      return
    }
    setEdgeMenuConnection(connection)
  }, [])
  const displayEdges = useMemo<Edge<ContextEdgeData>[]>(
    () => edges.map((edge) => {
      const edgeData = edge.data
      return {
        ...edge,
        data: {
          ...edgeData,
          hasTraceData: edgeData?.hasTraceData === true,
          contextJson: edgeData?.contextJson,
          sourcePhaseId: edgeData?.sourcePhaseId ?? edge.source,
          targetPhaseId: edgeData?.targetPhaseId ?? edge.target,
          onEdgeContextMenu: openEdgeContextMenu,
        },
      }
    }),
    [edges, openEdgeContextMenu],
  )

  const onConnect = useCallback((connection: Connection) => {
    const source = connection.source
    const target = connection.target
    if (!source || !target || source === INPUT_ID || source === OUTPUT_ID || target === INPUT_ID || target === OUTPUT_ID) {
      toast.error('Only phase nodes can be connected as dependencies')
      return
    }
    if (source === target) {
      toast.error('A phase cannot depend on itself')
      return
    }
    const sourceNode = phaseNodes.find((node) => node.id === source)
    const targetNode = phaseNodes.find((node) => node.id === target)
    if (!sourceNode || !targetNode) {
      toast.error('Both connection endpoints must be phase nodes')
      return
    }
    if (targetNode.data.dependsOn.includes(source)) {
      toast.error('This dependency already exists')
      return
    }

    setEdges((current) => addEdge({ ...connection, type: 'contextEdge' }, current))
    setNodes((current) => current.map((node) => {
      if (node.type !== 'skill' || node.id !== target || node.data.dependsOn.includes(source)) {
        return node
      }
      return {
        ...node,
        data: {
          ...node.data,
          dependsOn: [...node.data.dependsOn, source],
        }
      }
    }))
    if (onPersistConnection) {
      Promise.resolve(onPersistConnection(connection)).catch((persistError: unknown) => {
        toast.error(persistError instanceof Error ? persistError.message : 'Could not persist dependency')
        setEdges(layoutResult.edges)
        setNodes(layoutResult.nodes)
      })
    }
  }, [layoutResult.edges, layoutResult.nodes, onPersistConnection, phaseNodes, setEdges, setNodes])

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
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
        edges={displayEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onPaneContextMenu={(event) => {
          if (isEdgeContextTarget(event.target)) {
            return
          }
          setEdgeMenuConnection(null)
        }}
        onNodeContextMenu={() => {
          setEdgeMenuConnection(null)
        }}
        onEdgeContextMenu={(event, edge) => {
          openEdgeContextMenu(event, { source: edge.source, target: edge.target })
        }}
        onNodeClick={(_, node) => {
          setSelectedCanvasNodeId(node.id)
          if (node.type === 'skill') {
            onNodeSelect?.({ id: node.id, data: node.data })
            onPanelChange?.('properties')
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
            workspace?.onFileOpen(`${skillId}/GRAPH.md`)
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
          setReactFlowInstance(instance)
          fitViewRef.current = () => instance.fitView({ padding: 0.2 })
          fitLayout()
        }}
        nodeOrigin={CENTER_NODE_ORIGIN}
        fitView
        minZoom={0.35}
        maxZoom={1.4}
      >
        <Background gap={18} size={1} />
        <Controls position="bottom-left" />
        {!compact ? <MiniMap pannable zoomable position="bottom-right" style={{ height: 120, width: 200 }} /> : null}
      </ReactFlow>
        </section>
      </ContextMenuTrigger>
      <CanvasContextMenuContent
        edgeMenuConnection={edgeMenuConnection}
        onCreatePhase={onCreatePhase}
        onDisconnectConnection={onDisconnectConnection}
        onCloseEdgeMenu={() => setEdgeMenuConnection(null)}
      />
    </ContextMenu>
  )
}

export function CanvasContextMenuContent({
  edgeMenuConnection,
  onCreatePhase,
  onDisconnectConnection,
  onCloseEdgeMenu,
}: {
  edgeMenuConnection: { source: string; target: string } | null
  onCreatePhase?: (kind: NewPhaseKind) => Promise<void> | void
  onDisconnectConnection?: (connection: { source: string; target: string }) => Promise<void> | void
  onCloseEdgeMenu?: () => void
}) {
  return (
    <ContextMenuContent>
      {edgeMenuConnection ? (
        <ContextMenuItem
          onSelect={() => {
            void onDisconnectConnection?.(edgeMenuConnection)
            onCloseEdgeMenu?.()
          }}
        >
          Disconnect
        </ContextMenuItem>
      ) : (
        <ContextMenuSub>
          <ContextMenuSubTrigger>Add Phase Node</ContextMenuSubTrigger>
          <ContextMenuSubContent>
            <ContextMenuItem onSelect={() => { void onCreatePhase?.('skill') }}>
              Agent Phase
            </ContextMenuItem>
            <ContextMenuItem onSelect={() => { void onCreatePhase?.('logic') }}>
              Logic Phase
            </ContextMenuItem>
            <ContextMenuItem onSelect={() => { void onCreatePhase?.('subgraph') }}>
              Subgraph Phase
            </ContextMenuItem>
          </ContextMenuSubContent>
        </ContextMenuSub>
      )}
    </ContextMenuContent>
  )
}
