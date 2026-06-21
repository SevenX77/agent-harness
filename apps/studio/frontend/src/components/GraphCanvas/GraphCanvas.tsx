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
import type { ChildGraphTopology, CompileError, ErrorResponse, ResumeValidityResponse, SkillDetail } from '@/api/types'
import { getChildGraphTopology, getSkillDetail, writeSkillFile, type ResumeRunOptions } from '@/api/client'
import { isTauriRuntime } from '@/config/runtime'
import { resolveWorkspaceIdentity } from '@/components/studio/workspace-identity'
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
import { sha256Hex } from '@/lib/hash'
import { ContextEdge, type ContextEdgeData } from '@/components/edges/ContextEdge'
import { GlobalInputNode, GlobalOutputNode } from '@/components/nodes/GlobalInputOutputNode'
import { buildEdges, INPUT_ID, OUTPUT_ID, SkillNode, type GraphCanvasNode, type SkillGraphNode, type SkillGraphNodeData, type SkillNodeStatus } from '@/components/nodes'
import type { GoldenNodeState } from '@/components/studio/node-golden'
import { useOptionalWorkspaceContext } from '@/components/studio/WorkspaceContext'
import { HitlNodeToolbar } from '@/components/studio/HitlNodeToolbar'
import { ResumeNodeToolbar } from '@/components/studio/ResumeNodeToolbar'
import type { TraceHitlResumeRequest } from '@/components/studio/hitl-prompt'
import { normalizeAbsoluteSubgraphPath } from '@/components/studio/subgraph-path'
import type { PanelKind } from '@/components/studio/Toolbar'
import { buildNodes, buildNodesFromTopology, phaseKindFile } from './build-nodes'
import { nodeToFocus } from './canvas-focus'
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
import { isDrilledChildEditable, type ChildSaveTarget } from './drill-edit'

interface GraphCanvasProps {
  skillId: string
  // n2-canvas #14: the parent skill's absolute workspace root (its own skill dir).
  // Used to decide whether a drilled child subgraph is EDITABLE (lives under the
  // editable workspace) or READ-ONLY (a bundled/public skill) — see isDrilledChildEditable.
  workspaceRoot?: string | null
  skillDetail?: SkillDetail
  isLoading?: boolean
  error?: unknown
  selectedNodeId?: string | null
  onNodeSelect?: (node: { id: string, data: SkillGraphNodeData }) => void
  onPanelChange?: (panel: PanelKind | null) => void
  onCreatePhase?: (kind: NewPhaseKind) => Promise<void> | void
  // n2-canvas #14: every save handler takes an optional drilled-child `target`. When
  // editing INSIDE a drilled subgraph the canvas passes the child's own identity +
  // SkillDetail + child-refetch so the write/serialize/compile route to the CHILD
  // skill (not the parent). Absent target ⇒ parent/root edit, behaviour unchanged.
  onPersistConnection?: (connection: Connection, target?: ChildSaveTarget) => Promise<void> | void
  onDisconnectConnection?: (connection: { source: string; target: string }, target?: ChildSaveTarget) => Promise<void> | void
  // n2-canvas #8 (atomic reconnect): a single handler that applies BOTH the old
  // depends_on removal and the new depends_on addition in one serialize/write.
  // When provided it replaces the disconnect-then-persist chain (two round-trips)
  // that caused a 409 lost-update. Optional only as a defensive fallback; both
  // real consumers (main canvas + compact SplitEditor canvas) wire it.
  onReconnectConnection?: (
    disconnect: { source: string; target: string },
    connect: { source: string; target: string },
    target?: ChildSaveTarget,
  ) => Promise<void> | void
  statusByNodeId?: Record<string, SkillNodeStatus>
  compileErrorsByNodeId?: Record<string, CompileError[]>
  goldenStateByNodeId?: Record<string, GoldenNodeState>
  errorMessageByNodeId?: Record<string, string>
  // N5 atom #3 (dirty-downstream-graying): the resume-validity `affected_downstream`
  // node ids. Workspace derives this from the real validity response for the node
  // being resumed from; the canvas grays exactly these nodes (unrelated branches
  // stay normal). Empty/undefined when resume is clean or no node is being resumed.
  dirtyDownstreamNodeIds?: ReadonlySet<string>
  // N4 atom #9 (run-focus-follow): the phase id of the node currently running,
  // derived by Workspace from the same live run stream that colors the nodes
  // (statusByNodeId -> the node whose status is 'running'). When it changes the
  // canvas auto-centers on that node so the user's view follows the run. Not a
  // new derivation — pure wiring of the existing activeTracePhase.
  activeTracePhase?: string | null
  compact?: boolean
  onPhaseFileSave?: (args: { path: string; content: string; expectedHash: string }, target?: ChildSaveTarget) => Promise<void> | void
  // F4: when the run pauses for human input, the node-anchored HitL box submits
  // the answer through this callback (the same resume path the side panel uses).
  onSubmitHitlResponse?: (request: TraceHitlResumeRequest) => void
  hitlSubmitting?: boolean
  // N5 atom #2 (node-anchored-resume): when the selected node failed during a
  // run, anchor the [Resume] control ON that node (NodeToolbar) in addition to
  // the side panel. All driven by the same real run/validity state Workspace
  // already computes; the click routes through onResumeNode -> resumeRun.
  runId?: string | null
  resumeNodeStatus?: SkillNodeStatus | null
  resumeValidity?: ResumeValidityResponse | null
  resumeValidityLoading?: boolean
  resumeValidityError?: string | null
  resumeLoading?: boolean
  onResumeNode?: (options: ResumeRunOptions) => Promise<void> | void
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
  workspaceRoot,
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
  errorMessageByNodeId,
  dirtyDownstreamNodeIds,
  activeTracePhase,
  compact = false,
  onPhaseFileSave,
  onSubmitHitlResponse,
  hitlSubmitting = false,
  runId,
  resumeNodeStatus,
  resumeValidity,
  resumeValidityLoading = false,
  resumeValidityError,
  resumeLoading = false,
  onResumeNode,
}: GraphCanvasProps) {
  const workspace = useOptionalWorkspaceContext()
  const [expandedSubgraphs, setExpandedSubgraphs] = useState<Set<string>>(() => new Set())
  // N2 atom #15 (l3-step-edit): canvas-owned open/closed state for each AGENT
  // node's inline L3 step editor. Mirrors expandedSubgraphs; kept inside
  // GraphCanvas so the toggle never crosses the canvas boundary.
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(() => new Set())
  // R9: LOCAL drill-down focus stack. Empty = root graph (unchanged). When
  // non-empty the canvas focuses INTO the drilled child graph and a top-left
  // breadcrumb lets the user pop back up. Kept inside GraphCanvas (not lifted to
  // Workspace) so the navigation state never crosses the canvas boundary.
  const [drillStack, dispatchDrill] = useReducer(drillStackReducer, [] as DrillStack)
  const [childGraph, setChildGraph] = useState<ChildGraphTopology | null>(null)
  // n2-canvas #14: the drilled child's FULL SkillDetail (manifest/topology/files),
  // fetched in parallel with childGraph. Option A renders the drilled nodes with
  // buildNodes(childSkillId, childDetail, …) — reusing the root edit wiring — so the
  // child is a first-class EDITABLE graph keyed to its own identity, not a read-only
  // topology projection. Null until it resolves (the topology-only view renders meanwhile).
  const [childDetail, setChildDetail] = useState<SkillDetail | null>(null)
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

  // N2 atom #15: open/close an AGENT node's inline L3 step editor.
  const toggleSteps = useCallback((nodeId: string) => {
    setExpandedSteps((current) => {
      const next = new Set(current)
      if (next.has(nodeId)) {
        next.delete(nodeId)
      } else {
        next.add(nodeId)
      }
      return next
    })
  }, [])

  // N2 atom #15: persist an edited agent body through the normal phase-file save
  // path. The optimistic-lock hash is taken over the CURRENT (pre-edit) body —
  // the same snapshot the step transforms ran on — so a stale concurrent edit is
  // rejected by the backend hash guard rather than silently overwritten.
  const handleStepsSave = useCallback(
    async (_nodeId: string, filePath: string, currentBody: string, nextBody: string) => {
      if (!onPhaseFileSave) return
      // n2-canvas #14: inside an editable drilled child, route the body save to the
      // child target (read via ref so this stable callback need not depend on the
      // drill state). At root depth the target is null → parent save, unchanged.
      const childArgs = drilledChildTargetRef.current
        ? ([drilledChildTargetRef.current] as const)
        : ([] as const)
      try {
        const expectedHash = await sha256Hex(currentBody)
        await onPhaseFileSave({ path: filePath, content: nextBody, expectedHash }, ...childArgs)
      } catch (saveError) {
        toast.error('Could not save steps: ' + (saveError instanceof Error ? saveError.message : String(saveError)))
      }
    },
    [onPhaseFileSave],
  )

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

  // n2-canvas #14: load the drilled child's topology AND its full SkillDetail
  // (Option A). The detail is fetched against the CHILD's own resolved skillId
  // (derived from the topology-reported absolute child path), so the drilled nodes
  // become editable against the child identity. Extracted as a reusable callback so
  // a child write can re-fetch the child on settle/rollback (NOT parent revalidate).
  // `signal.cancelled` lets a superseded drill abort its late writes.
  const loadChildGraph = useCallback(async (path: string, signal: { cancelled: boolean }) => {
    setIsChildGraphLoading(true)
    setChildGraphError(null)
    try {
      const topology = await getChildGraphTopology(skillId, path)
      if (signal.cancelled) return
      setChildGraph(topology)
      const childSkillId = resolveWorkspaceIdentity(`local:${topology.path}`).skillId
      if (childSkillId) {
        try {
          const detail = await getSkillDetail(childSkillId)
          if (signal.cancelled) return
          setChildDetail(detail)
        } catch (detailError) {
          // The child topology rendered; its full detail (needed for in-place
          // editing) failed to load. Keep the read-only topology view and warn —
          // never silently degrade to a non-editable canvas with no signal.
          if (signal.cancelled) return
          console.warn('subgraph child detail failed to load; drilled view stays read-only', detailError)
          setChildDetail(null)
        }
      }
      setIsChildGraphLoading(false)
    } catch (error: unknown) {
      if (signal.cancelled) return
      setChildGraph(null)
      setChildDetail(null)
      setChildGraphError(childGraphErrorMessage(error, path))
      setIsChildGraphLoading(false)
    }
  }, [skillId])

  // Fetch the drilled child graph whenever the focused path changes. Empty
  // stack clears the child state so the root graph renders unchanged.
  const childLoadSignalRef = useRef<{ cancelled: boolean } | null>(null)
  useEffect(() => {
    if (!drilledPath) {
      setChildGraph(null)
      setChildDetail(null)
      setChildGraphError(null)
      setIsChildGraphLoading(false)
      childLoadSignalRef.current = null
      return
    }
    const signal = { cancelled: false }
    childLoadSignalRef.current = signal
    setChildGraph(null)
    setChildDetail(null)
    void loadChildGraph(drilledPath, signal)
    return () => {
      signal.cancelled = true
    }
  }, [drilledPath, loadChildGraph])

  // n2-canvas #14: re-fetch the drilled child after a child write settles (success
  // or failure). The optimistic edge state is restored from layoutResult (built
  // from childGraph) by the connect/reconnect catch handlers; this re-pulls the
  // child's last-known-good topology + detail so the canvas reflects the real
  // rolled-back / committed child state — the child analogue of mutateSkillDetail.
  const refetchChildGraph = useCallback(async () => {
    if (!drilledPath) return
    const signal = { cancelled: false }
    childLoadSignalRef.current = signal
    await loadChildGraph(drilledPath, signal)
  }, [drilledPath, loadChildGraph])
  const safeStatusByNodeId = useMemo(() => statusByNodeId ?? {}, [statusByNodeId])
  const safeCompileErrorsByNodeId = useMemo(() => compileErrorsByNodeId ?? {}, [compileErrorsByNodeId])
  const safeGoldenStateByNodeId = useMemo(() => goldenStateByNodeId ?? {}, [goldenStateByNodeId])
  const safeErrorMessageByNodeId = useMemo(() => errorMessageByNodeId ?? {}, [errorMessageByNodeId])
  const safeDirtyDownstreamNodeIds = useMemo(
    () => dirtyDownstreamNodeIds ?? new Set<string>(),
    [dirtyDownstreamNodeIds],
  )
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

  // n2-canvas #14: the drilled child's own save identity, derived purely on the FE
  // from the backend-resolved absolute child path (childGraph.path) — the SAME
  // resolution the removed project-switch escape hatch used. Null at root depth.
  const drilledChildIdentity = useMemo(
    () => (isDrilled && childGraph ? resolveWorkspaceIdentity(`local:${childGraph.path}`) : null),
    [isDrilled, childGraph],
  )
  // n2-canvas #14 (PM decision): a drilled child that resolves to a READ-ONLY
  // bundled/public skill (outside the editable workspace) is NOT editable in place
  // — block, don't auto-fork, don't silently mutate. Determined up front, path-based.
  const isDrilledChildReadOnly = useMemo(
    () => (childGraph ? !isDrilledChildEditable(childGraph.path, workspaceRoot ?? null, isTauriRuntime()) : false),
    [childGraph, workspaceRoot],
  )
  // n2-canvas #14: the child save target threaded into the save handlers when an
  // edit happens inside an EDITABLE drilled child. Null when at root, when the
  // child detail hasn't loaded, or when the child is read-only (edits are blocked).
  const drilledChildTarget = useMemo<ChildSaveTarget | null>(
    () => (isDrilled && !isDrilledChildReadOnly && childDetail && drilledChildIdentity?.skillId
      ? {
          skillId: drilledChildIdentity.skillId,
          workspaceRoot: drilledChildIdentity.workspaceRoot,
          detail: childDetail,
          onSettled: refetchChildGraph,
        }
      : null),
    [isDrilled, isDrilledChildReadOnly, childDetail, drilledChildIdentity, refetchChildGraph],
  )
  const drilledChildTargetRef = useRef<ChildSaveTarget | null>(null)
  useEffect(() => {
    drilledChildTargetRef.current = drilledChildTarget
  }, [drilledChildTarget])
  // n2-canvas #14: connect/reconnect affordances are live when the canvas is the
  // main (non-compact) editor AND, if drilled, the child is editable (not a
  // read-only bundled/public subgraph). A read-only drilled child renders but
  // cannot start a structure edit (the PM read-only block).
  const canEditCanvas = !compact && !(isDrilled && isDrilledChildReadOnly)

  // N2 atom #15: the inline L3 step-editor inputs threaded into AGENT nodes.
  // compact = read-only projection: withhold the in-node edit callbacks so the
  // "Edit steps" affordance never renders on the mini-canvas (canEditSteps keys
  // on onToggleSteps being a function). Only the read-only dirty-downstream
  // graying is kept — editing the body stays on the main canvas.
  const agentStepsInputs = useMemo(
    () => ({
      expandedSteps: compact ? undefined : expandedSteps,
      onToggleSteps: compact ? undefined : toggleSteps,
      onStepsSave: compact ? undefined : handleStepsSave,
      dirtyDownstreamNodeIds: safeDirtyDownstreamNodeIds,
    }),
    [compact, expandedSteps, toggleSteps, handleStepsSave, safeDirtyDownstreamNodeIds],
  )
  const rawNodes = useMemo(() => {
    // R9 / n2-canvas #14: when focused into a child graph, render its real phases.
    // Status overlays (which key on ROOT phase ids) are dropped at depth.
    if (isDrilled) {
      if (!childGraph) return []
      // The drilled nodes key to the CHILD's own skillId so edits/file opens resolve
      // against the child, not the parent. Edit affordances are withheld for a
      // read-only child (empty agentSteps), realising the PM read-only block.
      const childNodeSkillId = drilledChildIdentity?.skillId ?? skillId
      const childAgentSteps = isDrilledChildReadOnly ? {} : agentStepsInputs
      // Option A: once the child's full SkillDetail loads, render it as a
      // first-class editable graph with buildNodes (reusing the root edit wiring).
      // Until then, render the topology-only projection (loading/fallback path).
      if (childDetail && !isDrilledChildReadOnly) {
        return buildNodes(childNodeSkillId, childDetail, expandedSubgraphs, toggleSubgraph, {}, {}, {}, {}, childAgentSteps)
      }
      return buildNodesFromTopology(childNodeSkillId, childGraph.phases, childGraph.graph_topology, {}, childAgentSteps)
    }
    return buildNodes(skillId, skillDetail, expandedSubgraphs, toggleSubgraph, safeStatusByNodeId, safeCompileErrorsByNodeId, safeGoldenStateByNodeId, safeErrorMessageByNodeId, agentStepsInputs)
  }, [agentStepsInputs, childDetail, childGraph, drilledChildIdentity, expandedSubgraphs, isDrilled, isDrilledChildReadOnly, safeStatusByNodeId, safeCompileErrorsByNodeId, safeGoldenStateByNodeId, safeErrorMessageByNodeId, skillDetail, skillId, toggleSubgraph])
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

  // N4 atom #9 (run-focus-follow): when the run advances to a new node,
  // auto-center the viewport on it. `activeTracePhase` is the live "running"
  // node Workspace derives from the run stream; nodeToFocus only confirms a
  // matching node exists on the canvas before centering, so we never fitView
  // onto a phase id with no node (e.g. drilled child, INPUT/OUTPUT). Mirrors the
  // conflict-warning pan effect above; no timer/listener so no cleanup needed.
  const lastFocusedPhaseRef = useRef<string | null>(null)
  useEffect(() => {
    if (!reactFlowInstance) {
      return
    }
    // Only re-center when the RUNNING phase actually changes — not on every status
    // overlay tick or user node-drag (which both churn the `nodes` reference). Read
    // node existence at fire time via getNodes() so `nodes` stays out of the deps,
    // otherwise a live run would keep snapping the viewport back and fight a manual pan.
    if ((activeTracePhase ?? null) === lastFocusedPhaseRef.current) {
      return
    }
    const focusId = nodeToFocus(activeTracePhase, reactFlowInstance.getNodes().map((node) => node.id))
    if (!focusId) {
      return
    }
    lastFocusedPhaseRef.current = activeTracePhase ?? null
    reactFlowInstance.fitView({
      nodes: [{ id: focusId }],
      duration: 600,
      padding: 0.8,
    })
  }, [activeTracePhase, reactFlowInstance])

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

  // n2-canvas #14: a drilled subgraph that is read-only (bundled/public) — or whose
  // editable child detail has not resolved yet — must NOT accept a structure edit.
  // Block BEFORE any optimistic mutation so the canvas never writes against the
  // wrong identity nor silently mutates a bundle. Returns true when the edit is
  // blocked. At root depth (not drilled) this is a no-op.
  const blockDrilledEditIfUnwritable = useCallback((): boolean => {
    if (!isDrilled) return false
    if (drilledChildTarget) return false
    if (isDrilledChildReadOnly) {
      toast.error('This subgraph is read-only — fork it into your workspace to edit.')
    } else {
      toast.error('Loading subgraph — try again in a moment.')
    }
    return true
  }, [isDrilled, drilledChildTarget, isDrilledChildReadOnly])

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
    if (blockDrilledEditIfUnwritable()) {
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
      // n2-canvas #14: pass the drilled-child target ONLY when drilled; at root
      // depth the call is the original single-arg form (byte-identical, no
      // trailing undefined), so root persist behavior is unchanged.
      const childArgs = drilledChildTarget ? ([drilledChildTarget] as const) : ([] as const)
      Promise.resolve(onPersistConnection(connection, ...childArgs)).catch((persistError: unknown) => {
        toast.error(persistError instanceof Error ? persistError.message : 'Could not persist dependency')
        setEdges(layoutResult.edges)
        setNodes(layoutResult.nodes)
      })
    }
  }, [blockDrilledEditIfUnwritable, drilledChildTarget, layoutResult.edges, layoutResult.nodes, onPersistConnection, phaseNodes, setEdges, setNodes])

  // R4 + n2-canvas #8: drag an existing edge endpoint to a new node = remove the
  // old dependency + add the new one. planEdgeReconnect owns the DECISION (global
  // node / self-dependency / no-op guards). The MUTATION is now a SINGLE atomic
  // serialize/write through onReconnectConnection: the previous code chained
  // onDisconnectConnection().then(onPersistConnection), two serialize round-trips
  // against the same captured skillDetail closure, and the queued persist
  // serialized the pre-disconnect phases with a stale expected_hash → backend 409
  // lost-update that left the graph half-mutated. A reconnect that lands back on
  // the same endpoints (no-op) just snaps the edge back without a write. Both
  // real consumers (main canvas + compact SplitEditor canvas) now wire
  // onReconnectConnection; the legacy chained fallback below is kept only as a
  // defensive path for any future surface that mounts GraphCanvas without it.
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
    if (blockDrilledEditIfUnwritable()) {
      return
    }

    // Optimistically move the edge to its new endpoints before the write lands.
    setEdges((current) => reconnectEdge(oldEdge, newConnection, current))
    const rollback = (reconnectError: unknown) => {
      toast.error(reconnectError instanceof Error ? reconnectError.message : 'Could not reconnect dependency')
      setEdges(layoutResult.edges)
      setNodes(layoutResult.nodes)
    }
    // n2-canvas #14: spread the child target ONLY when drilled; at root depth
    // these stay the original arg forms (no trailing undefined), so the existing
    // root reconnect/disconnect contract is byte-identical.
    const childArgs = drilledChildTarget ? ([drilledChildTarget] as const) : ([] as const)
    if (onReconnectConnection) {
      Promise.resolve(onReconnectConnection(plan.disconnect, plan.connect, ...childArgs)).catch(rollback)
      return
    }
    if (!onDisconnectConnection || !onPersistConnection) {
      return
    }
    Promise.resolve(onDisconnectConnection(plan.disconnect, ...childArgs))
      .then(() => onPersistConnection({ ...newConnection, source: plan.connect.source, target: plan.connect.target }, ...childArgs))
      .catch(rollback)
  }, [blockDrilledEditIfUnwritable, drilledChildTarget, layoutResult.edges, layoutResult.nodes, onDisconnectConnection, onPersistConnection, onReconnectConnection, phaseNodes, setEdges, setNodes])

  const onReconnectStart = useCallback(() => {
    reconnectLandedRef.current = false
  }, [])

  // n2-canvas #14: the right-click "Disconnect" menu path. Routes through the same
  // drilled-child target + read-only block as the drag-disconnect path so a menu
  // disconnect inside a drilled child writes the CHILD's GRAPH.md, and a read-only
  // child is blocked. At root depth this is the plain parent disconnect, unchanged.
  const handleMenuDisconnect = useCallback((connection: { source: string; target: string }) => {
    if (!onDisconnectConnection) return
    if (blockDrilledEditIfUnwritable()) return
    const childArgs = drilledChildTarget ? ([drilledChildTarget] as const) : ([] as const)
    void Promise.resolve(onDisconnectConnection(connection, ...childArgs))
      .catch((disconnectError: unknown) => {
        toast.error(disconnectError instanceof Error ? disconnectError.message : 'Could not disconnect dependency')
      })
  }, [blockDrilledEditIfUnwritable, drilledChildTarget, onDisconnectConnection])

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
    if (blockDrilledEditIfUnwritable()) {
      return
    }
    setEdges((current) => current.filter((candidate) => candidate.id !== edge.id))
    const childArgs = drilledChildTarget ? ([drilledChildTarget] as const) : ([] as const)
    Promise.resolve(onDisconnectConnection({ source: edge.source, target: edge.target }, ...childArgs))
      .catch((disconnectError: unknown) => {
        toast.error(disconnectError instanceof Error ? disconnectError.message : 'Could not disconnect dependency')
        setEdges(layoutResult.edges)
        setNodes(layoutResult.nodes)
      })
  }, [blockDrilledEditIfUnwritable, drilledChildTarget, layoutResult.edges, layoutResult.nodes, onDisconnectConnection, setEdges, setNodes])

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

      {/* compact = the SplitEditor mini-canvas: a READ-ONLY projection of
          GRAPH.md, never a second editor. Editing (connect / reconnect / delete)
          stays on the main canvas, so two canvases can't race writes to GRAPH.md
          off independent snapshots (the stale-hash 409 class). */}
      <ReactFlow
        nodes={selectedNodes}
        edges={displayEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodesConnectable={canEditCanvas}
        nodesDraggable={!compact}
        deleteKeyCode={compact ? null : undefined}
        onConnect={compact ? undefined : onConnect}
        edgesReconnectable={canEditCanvas}
        onReconnectStart={compact ? undefined : onReconnectStart}
        onReconnect={compact ? undefined : onReconnect}
        onReconnectEnd={compact ? undefined : onReconnectEnd}
        onPaneContextMenu={(event) => {
          if (isEdgeContextTarget(event.target)) {
            return
          }
          setEdgeMenuConnection(null)
        }}
        onNodeContextMenu={() => {
          setEdgeMenuConnection(null)
        }}
        onEdgeContextMenu={compact ? undefined : (event, edge) => {
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
            // R9: double-clicking a NESTED subgraph node focuses INTO its child
            // graph in-place (drill DEEPER); non-subgraph phases open their source
            // file as before. Unchanged at any depth.
            const subgraphPath = normalizeAbsoluteSubgraphPath(node.data.subgraphPath)
            if (subgraphPath) {
              drillInto(subgraphPath, node.data.label)
              return
            }
            // n2-canvas #14 (edit write-back): while drilled, a leaf (non-subgraph)
            // child node belongs to the CHILD subgraph and is edited IN PLACE — no
            // project switch. The node's data.skillId is already the CHILD's own id
            // (the drilled build keys nodes to the child identity) and its filePath
            // is child-relative, so opening `${node.data.skillId}/<filePath>`
            // resolves the child's real file. The removed pushNavSkill escape hatch
            // (which swapped the whole Workspace to the child as a standalone
            // project) is gone — drilled editing stays on the same canvas.
            onNodeSelect?.({ id: node.id, data: node.data })
            const openSkillId = node.data.skillId || skillId
            workspace?.onFileOpen(`${openSkillId}/${node.data.filePath ?? `phases/${node.id}/${phaseKindFile(node.data)}`}`)
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
        {/* N5 #2: node-anchored [Resume] for the selected failed node. Driven by
            the same real run/validity state the side panel uses; coexists with
            the global top-bar Resume. */}
        <ResumeNodeToolbar
          runId={runId ?? null}
          nodeId={selectedNodeId ?? null}
          nodeStatus={resumeNodeStatus ?? null}
          resumeValidity={resumeValidity ?? null}
          loading={resumeValidityLoading}
          error={resumeValidityError ?? null}
          resumeLoading={resumeLoading}
          onResumeNode={onResumeNode}
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
              {onCreatePhase && !isDrilled && !compact ? <AddPhaseControl onCreatePhase={onCreatePhase} /> : null}
              {!isDrilled && !compact ? (
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
        onCreatePhase={isDrilled ? undefined : onCreatePhase}
        onDisconnectConnection={handleMenuDisconnect}
        onCloseEdgeMenu={() => setEdgeMenuConnection(null)}
        readOnly={compact}
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
  readOnly,
}: {
  edgeMenuConnection: { source: string; target: string } | null
  onCreatePhase?: (kind: NewPhaseKind) => Promise<void> | void
  onDisconnectConnection?: (connection: { source: string; target: string }) => Promise<void> | void
  onCloseEdgeMenu?: () => void
  readOnly?: boolean
}) {
  // Read-only projection (compact mini-canvas): no edit affordances at all, so
  // right-click offers neither Disconnect nor Add Phase Node.
  if (readOnly) {
    return null
  }
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
