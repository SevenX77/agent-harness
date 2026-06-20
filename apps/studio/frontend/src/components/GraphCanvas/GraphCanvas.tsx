import '@xyflow/react/dist/style.css'

import {
  Background,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  addEdge,
  reconnectEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type FinalConnectionState,
  type ReactFlowInstance,
} from '@xyflow/react'
import { FileCog, Plus } from 'lucide-react'
import { useCallback, useEffect, useMemo, useReducer, useRef, useState, type MouseEvent } from 'react'
import { toast } from 'sonner'
import { AxiosError } from 'axios'
import type { ChildGraphTopology, CompileError, ErrorResponse, SkillDetail } from '@/api/types'
import { getChildGraphTopology, writeSkillFile } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import { MacroContractDrawer } from '@/components/macroform/MacroContractDrawer'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { CycleDetectedError, getAutoLayoutedElements } from '@/lib/layout'
import { ContextEdge, type ContextEdgeData } from '@/components/edges/ContextEdge'
import { GlobalInputNode, GlobalOutputNode } from '@/components/nodes/GlobalInputOutputNode'
import { buildEdges, INPUT_ID, OUTPUT_ID, SkillNode, type GraphCanvasNode, type SkillGraphNode, type SkillGraphNodeData, type SkillNodeStatus } from '@/components/nodes'
import type { GoldenNodeState } from '@/components/studio/node-golden'
import { useOptionalWorkspaceContext } from '@/components/studio/WorkspaceContext'
import { HitlNodeToolbar } from '@/components/studio/HitlNodeToolbar'
import type { TraceHitlResumeRequest } from '@/components/studio/hitl-prompt'
import { normalizeAbsoluteSubgraphPath } from '@/components/studio/subgraph-path'
import type { PanelKind } from '@/components/studio/Toolbar'
import { buildNodes, buildNodesFromTopology, phaseKindFile } from './build-nodes'
import {
  type NewPhaseKind,
  checkSequentialOverwrites,
  addSequentialOverwriteField,
  phaseRefsFromSkillDetail,
  phaseFilePath,
  planEdgeReconnect,
  type OverwriteConflict,
} from './canvas-authoring'
import { DrillBreadcrumb } from './DrillBreadcrumb'
import { drillStackReducer, type DrillStack } from './drill-stack'

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
  // n2-canvas #8 (atomic reconnect): a single handler that applies BOTH the old
  // depends_on removal and the new depends_on addition in one serialize/write.
  // When provided it replaces the disconnect-then-persist chain (two round-trips)
  // that caused a 409 lost-update. Optional so the compact SplitEditor canvas,
  // which has not wired it, falls back to the legacy chained behavior.
  onReconnectConnection?: (
    disconnect: { source: string; target: string },
    connect: { source: string; target: string },
  ) => Promise<void> | void
  statusByNodeId?: Record<string, SkillNodeStatus>
  compileErrorsByNodeId?: Record<string, CompileError[]>
  goldenStateByNodeId?: Record<string, GoldenNodeState>
  compact?: boolean
  onPhaseFileSave?: (args: { path: string; content: string; expectedHash: string }) => Promise<void> | void
  // F4: when the run pauses for human input, the node-anchored HitL box submits
  // the answer through this callback (the same resume path the side panel uses).
  onSubmitHitlResponse?: (request: TraceHitlResumeRequest) => void
  hitlSubmitting?: boolean
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

/** Map a child-topology resolver failure to a human-readable drill error. */
function childGraphErrorMessage(error: unknown, path: string): string {
  if (error instanceof AxiosError) {
    const status = error.response?.status
    const body = error.response?.data as Partial<ErrorResponse> | undefined
    if (status === 404) {
      return `subgraph not found at ${path}`
    }
    if (body?.message) {
      return body.message
    }
  }
  return `Failed to load subgraph at ${path}`
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
  onReconnectConnection,
  statusByNodeId,
  compileErrorsByNodeId,
  goldenStateByNodeId,
  compact = false,
  onPhaseFileSave,
  onSubmitHitlResponse,
  hitlSubmitting = false,
}: GraphCanvasProps) {
  const workspace = useOptionalWorkspaceContext()
  const [expandedSubgraphs, setExpandedSubgraphs] = useState<Set<string>>(() => new Set())
  // R9: LOCAL drill-down focus stack. Empty = root graph (unchanged). When
  // non-empty the canvas focuses INTO the drilled child graph and a top-left
  // breadcrumb lets the user pop back up. Kept inside GraphCanvas (not lifted to
  // Workspace) so the navigation state never crosses the canvas boundary.
  const [drillStack, dispatchDrill] = useReducer(drillStackReducer, [] as DrillStack)
  const [childGraph, setChildGraph] = useState<ChildGraphTopology | null>(null)
  const [childGraphError, setChildGraphError] = useState<string | null>(null)
  const [isChildGraphLoading, setIsChildGraphLoading] = useState(false)
  const [selectedCanvasNodeId, setSelectedCanvasNodeId] = useState<string | null>(null)
  // n2 #22: the structured GRAPH.md macro-contract form (header scalars + phases
  // list). Opened from the top-left toolbar; raw GRAPH.md double-click (#23)
  // stays available untouched.
  const [macroFormOpen, setMacroFormOpen] = useState(false)
  const [edgeMenuConnection, setEdgeMenuConnection] = useState<{ source: string; target: string } | null>(null)
  const [canvasHeight, setCanvasHeight] = useState(0)
  const canvasRef = useRef<HTMLElement | null>(null)
  // R4 reconnect: set true the moment a dragged edge endpoint lands on a valid
  // handle (onReconnect). onReconnectEnd reads it to tell "moved to a new node"
  // (reconnect, already handled) apart from "dropped off any handle"
  // (drag-disconnect). Reset on every reconnect start.
  const reconnectLandedRef = useRef(false)

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

  // R9: drill INTO a subgraph node (push a focus level). The drilled child
  // topology is fetched by the effect below.
  const drillInto = useCallback((path: string, label: string) => {
    dispatchDrill({ type: 'push', level: { path, label } })
  }, [])
  // Pop back to a breadcrumb index (-1 = root graph).
  const drillNavigate = useCallback((index: number) => {
    dispatchDrill({ type: 'popTo', index })
  }, [])

  const drilledLevel = drillStack.length > 0 ? drillStack[drillStack.length - 1] : null
  const drilledPath = drilledLevel?.path ?? null

  // Fetch the drilled child graph whenever the focused path changes. Empty
  // stack clears the child state so the root graph renders unchanged.
  useEffect(() => {
    if (!drilledPath) {
      setChildGraph(null)
      setChildGraphError(null)
      setIsChildGraphLoading(false)
      return
    }
    let cancelled = false
    setIsChildGraphLoading(true)
    setChildGraphError(null)
    setChildGraph(null)
    getChildGraphTopology(skillId, drilledPath)
      .then((topology) => {
        if (cancelled) return
        setChildGraph(topology)
        setIsChildGraphLoading(false)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setChildGraph(null)
        setChildGraphError(childGraphErrorMessage(error, drilledPath))
        setIsChildGraphLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [skillId, drilledPath])
  const safeStatusByNodeId = useMemo(() => statusByNodeId ?? {}, [statusByNodeId])
  const safeCompileErrorsByNodeId = useMemo(() => compileErrorsByNodeId ?? {}, [compileErrorsByNodeId])
  const safeGoldenStateByNodeId = useMemo(() => goldenStateByNodeId ?? {}, [goldenStateByNodeId])
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

  const isDrilled = drilledPath !== null
  const rawNodes = useMemo(() => {
    // R9: when focused into a child graph, render its real phases/topology;
    // status overlays (which key on root phase ids) are dropped at depth.
    if (isDrilled) {
      if (!childGraph) return []
      return buildNodesFromTopology(skillId, childGraph.phases, childGraph.graph_topology, {})
    }
    return buildNodes(skillId, skillDetail, expandedSubgraphs, toggleSubgraph, safeStatusByNodeId, safeCompileErrorsByNodeId, safeGoldenStateByNodeId)
  }, [childGraph, expandedSubgraphs, isDrilled, safeStatusByNodeId, safeCompileErrorsByNodeId, safeGoldenStateByNodeId, skillDetail, skillId, toggleSubgraph])
  const phaseNodes = useMemo(
    () => rawNodes.filter((node): node is SkillGraphNode => node.type === 'skill'),
    [rawNodes],
  )
  // Trace events drive hasTraceData: an edge lights up only when the active run
  // actually dispatched data across it (matching input_dispatch event).
  const traceEvents = workspace?.traceEvents
  // No nodes at all (e.g. drilled child still loading) → no edges, so we never
  // emit a phantom INPUT→OUTPUT edge against a node-less canvas.
  const rawEdges = useMemo(
    () => (rawNodes.length === 0 ? [] : buildEdges(phaseNodes, traceEvents)),
    [phaseNodes, rawNodes.length, traceEvents],
  )
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

  // R4 + n2-canvas #8: drag an existing edge endpoint to a new node = remove the
  // old dependency + add the new one. planEdgeReconnect owns the DECISION (global
  // node / self-dependency / no-op guards). The MUTATION is now a SINGLE atomic
  // serialize/write through onReconnectConnection: the previous code chained
  // onDisconnectConnection().then(onPersistConnection), two serialize round-trips
  // against the same captured skillDetail closure, and the queued persist
  // serialized the pre-disconnect phases with a stale expected_hash → backend 409
  // lost-update that left the graph half-mutated. A reconnect that lands back on
  // the same endpoints (no-op) just snaps the edge back without a write. When
  // onReconnectConnection is not wired (the compact SplitEditor canvas), we keep
  // the legacy chained fallback so that surface still functions.
  const onReconnect = useCallback((oldEdge: Edge<ContextEdgeData>, newConnection: Connection) => {
    reconnectLandedRef.current = true
    const plan = planEdgeReconnect(
      { source: oldEdge.source, target: oldEdge.target },
      { source: newConnection.source, target: newConnection.target },
    )
    if (!plan.ok) {
      if (plan.reason !== 'no-op') {
        toast.error(plan.message)
      }
      return
    }
    const targetNode = phaseNodes.find((node) => node.id === plan.connect.target)
    if (targetNode && targetNode.data.dependsOn.includes(plan.connect.source)) {
      toast.error('This dependency already exists')
      return
    }

    // Optimistically move the edge to its new endpoints before the write lands.
    setEdges((current) => reconnectEdge(oldEdge, newConnection, current))
    const rollback = (reconnectError: unknown) => {
      toast.error(reconnectError instanceof Error ? reconnectError.message : 'Could not reconnect dependency')
      setEdges(layoutResult.edges)
      setNodes(layoutResult.nodes)
    }
    if (onReconnectConnection) {
      Promise.resolve(onReconnectConnection(plan.disconnect, plan.connect)).catch(rollback)
      return
    }
    if (!onDisconnectConnection || !onPersistConnection) {
      return
    }
    Promise.resolve(onDisconnectConnection(plan.disconnect))
      .then(() => onPersistConnection({ ...newConnection, source: plan.connect.source, target: plan.connect.target }))
      .catch(rollback)
  }, [layoutResult.edges, layoutResult.nodes, onDisconnectConnection, onPersistConnection, onReconnectConnection, phaseNodes, setEdges, setNodes])

  const onReconnectStart = useCallback(() => {
    reconnectLandedRef.current = false
  }, [])

  // R4: an edge endpoint dragged off every handle and released (isValid not
  // true, and no onReconnect fired) = the user pulled the wire loose, so drop
  // the dependency via the same disconnect → serialize path.
  const onReconnectEnd = useCallback((
    _event: globalThis.MouseEvent | globalThis.TouchEvent,
    edge: Edge<ContextEdgeData>,
    _handleType: 'source' | 'target',
    connectionState: FinalConnectionState,
  ) => {
    if (reconnectLandedRef.current || connectionState.isValid === true) {
      return
    }
    if (edge.source === INPUT_ID || edge.source === OUTPUT_ID || edge.target === INPUT_ID || edge.target === OUTPUT_ID) {
      return
    }
    if (!onDisconnectConnection) {
      return
    }
    setEdges((current) => current.filter((candidate) => candidate.id !== edge.id))
    Promise.resolve(onDisconnectConnection({ source: edge.source, target: edge.target }))
      .catch((disconnectError: unknown) => {
        toast.error(disconnectError instanceof Error ? disconnectError.message : 'Could not disconnect dependency')
        setEdges(layoutResult.edges)
        setNodes(layoutResult.nodes)
      })
  }, [layoutResult.edges, layoutResult.nodes, onDisconnectConnection, setEdges, setNodes])

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
        edgesReconnectable
        onReconnectStart={onReconnectStart}
        onReconnect={onReconnect}
        onReconnectEnd={onReconnectEnd}
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
            // R9: double-clicking a subgraph node focuses INTO its child graph
            // in-place; non-subgraph phases open their source file as before.
            const subgraphPath = normalizeAbsoluteSubgraphPath(node.data.subgraphPath)
            if (subgraphPath) {
              drillInto(subgraphPath, node.data.label)
              return
            }
            // R9 edit write-back: while drilled, a leaf (non-subgraph) child
            // node belongs to the CHILD subgraph, not the parent `skillId`. Its
            // file/GRAPH.md serialize/compile scope must run against the child's
            // own identity, so entering it opens the child as its own editable
            // skill (the nav-stack breadcrumb pops back up). Opening directly
            // under the parent `skillId` would resolve a non-existent file in
            // the wrong skill's file map. At root depth the in-place open path
            // is unchanged.
            if (isDrilled && drilledPath) {
              // The child path is an absolute workspace root; `local:` marks it
              // as a local-workspace selection (same form WelcomePage records),
              // which `resolveWorkspaceIdentity` resolves to the child's own
              // skillId + workspaceRoot.
              workspace?.pushNavSkill(`local:${drilledPath}`)
              return
            }
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
        {/* F4: node-anchored HitL input. Reads the live run stream from the
            workspace context (same array the edges already consume) and anchors
            a floating answer box above whichever node paused for human input. */}
        <HitlNodeToolbar
          traceEvents={workspace?.traceEvents ?? []}
          submitting={hitlSubmitting}
          onSubmitHitlResponse={onSubmitHitlResponse}
        />
        <Controls position="bottom-left" />
        {!compact ? <MiniMap pannable zoomable position="bottom-right" style={{ height: 120, width: 200 }} /> : null}
        {(onCreatePhase && !isDrilled) || drillStack.length > 0 ? (
          <Panel position="top-left">
            <div className="flex flex-col items-start gap-2">
              {drillStack.length > 0 ? (
                <DrillBreadcrumb
                  stack={drillStack}
                  rootLabel={skillDetail?.manifest.name ?? skillId}
                  onNavigate={drillNavigate}
                />
              ) : null}
              {isChildGraphLoading ? (
                <div className="inline-flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-muted-foreground shadow-sm">
                  <Spinner className="size-3" />
                  <span>Loading subgraph…</span>
                </div>
              ) : null}
              {childGraphError ? (
                <div className="rounded-md border border-destructive/40 bg-destructive/10 px-2.5 py-1.5 text-xs text-destructive shadow-sm">
                  {childGraphError}
                </div>
              ) : null}
              {onCreatePhase && !isDrilled ? <AddPhaseControl onCreatePhase={onCreatePhase} /> : null}
              {!isDrilled ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="shadow-sm"
                  aria-label="Edit macro contract"
                  onClick={() => setMacroFormOpen(true)}
                >
                  <FileCog className="size-3.5" />
                  Macro contract
                </Button>
              ) : null}
            </div>
          </Panel>
        ) : null}
      </ReactFlow>
        </section>
      </ContextMenuTrigger>
      <CanvasContextMenuContent
        edgeMenuConnection={edgeMenuConnection}
        onCreatePhase={onCreatePhase}
        onDisconnectConnection={onDisconnectConnection}
        onCloseEdgeMenu={() => setEdgeMenuConnection(null)}
      />
      <Sheet open={macroFormOpen} onOpenChange={setMacroFormOpen}>
        <SheetContent side="right" className="w-[26rem] gap-0 p-0 sm:max-w-md">
          <SheetHeader className="border-b border-border">
            <SheetTitle>Macro contract</SheetTitle>
            <SheetDescription>
              Edit the GRAPH.md header (name, schema version, LLM role, description) and the phases list.
            </SheetDescription>
          </SheetHeader>
          <ScrollArea className="min-h-0 flex-1">
            <div className="p-4">
              <MacroContractDrawer
                skillId={skillId}
                skillDetail={skillDetail}
                writeFile={(path, content, expectedHash) => writeSkillFile(skillId, path, content, expectedHash)}
              />
            </div>
          </ScrollArea>
        </SheetContent>
      </Sheet>
    </ContextMenu>
  )
}

const ADD_PHASE_OPTIONS: ReadonlyArray<{ kind: NewPhaseKind; label: string }> = [
  { kind: 'skill', label: 'Agent Phase' },
  { kind: 'logic', label: 'Logic Phase' },
  { kind: 'subgraph', label: 'Subgraph Phase' },
]

export function AddPhaseControl({
  onCreatePhase,
}: {
  onCreatePhase: (kind: NewPhaseKind) => Promise<void> | void
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" size="sm" variant="outline" className="shadow-sm" aria-label="Add phase">
          <Plus className="size-3.5" />
          Add phase
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {ADD_PHASE_OPTIONS.map((option) => (
          <DropdownMenuItem key={option.kind} onSelect={() => { void onCreatePhase(option.kind) }}>
            {option.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
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
