import '@xyflow/react/dist/style.css'

import {
  Background,
  MiniMap,
  Panel,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  useUpdateNodeInternals,
  type Connection,
  type Edge,
  type FinalConnectionState,
  type NodeChange,
  type ReactFlowInstance,
} from '@xyflow/react'
import { Trash2 } from 'lucide-react'
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState, type MouseEvent } from 'react'
import { toast } from 'sonner'
import { AxiosError } from 'axios'
import type { ChildGraphTopology, CompileError, ErrorResponse, ResumeValidityResponse, SkillDetail } from '@/api/types'
import { getChildGraphTopology, getSkillDetail, type ResumeRunOptions } from '@/api/client'
import { isTauriRuntime } from '@/config/runtime'
import { resolveWorkspaceIdentity, topLevelSkillIdFromWorkspaceRoot } from '@/components/studio/workspace-identity'
import { Spinner } from '@/components/ui/spinner'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuLabel,
  ContextMenuSeparator,
  ContextMenuShortcut,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
import { CycleDetectedError, getAutoLayoutedElements } from '@/lib/layout'
import { sha256Hex } from '@/lib/hash'
import { ContextEdge, type ContextEdgeData } from '@/components/edges/ContextEdge'
import { SubgraphBridgeEdge } from '@/components/edges/SubgraphBridgeEdge'
import { SubgraphGroupNode } from '@/components/nodes/SubgraphGroupNode'
import { buildEdges, createContextEdge, GlobalInputNode, GlobalOutputNode, INPUT_ID, OUTPUT_ID, SkillNode, type GraphCanvasNode, type SkillGraphNode, type SkillGraphNodeData, type SkillNodeStatus } from '@/components/nodes'
import { SUBGRAPH_BRIDGE_EDGE_TYPE } from '@/components/nodes/subgraph-bridge-handles'
import { buildSubgraphExpansion, positionedParentNodes, subgraphGroupNodeId, subgraphNodeIdChain, subgraphRevealNodeIds, type ExpandedSubgraphView, type SubgraphExpansionRequest } from '@/components/GraphCanvas/subgraph-expansion'
import type { GoldenNodeState } from '@/components/studio/node-golden'
import { useOptionalWorkspaceContext, type EdgeContextJson } from '@/components/studio/WorkspaceContext'
import type { FileOpenInput, FileOpenRequest } from '@/components/studio/file-types'
import { HitlNodeToolbar } from '@/components/studio/HitlNodeToolbar'
import { ResumeNodeToolbar } from '@/components/studio/ResumeNodeToolbar'
import type { TraceHitlResumeRequest } from '@/components/studio/hitl-prompt'
import { resolveSubgraphPath } from '@/components/studio/subgraph-path'
import { edgeContextFromEvents } from '@/lib/edge-context'
import { staticEdgeInference } from '@/lib/edge-static-inference'
import { errorMessage } from '@/utils/errors'
import type { PanelKind } from '@/components/studio/Toolbar'
import { buildNodes, buildNodesFromTopology, phaseKindFile } from './build-nodes'
import {
  type NewPhaseKind,
  addSequentialOverwriteField,
  defaultPhaseId,
  phaseRefsFromSkillDetail,
  phaseFilePath,
  planEdgeReconnect,
  type OverwriteConflict,
} from './canvas-authoring'
import { DrillBreadcrumb } from './DrillBreadcrumb'
import { drillStackReducer, type DrillStack } from './drill-stack'
import { isDrilledChildEditable, type ChildSaveTarget } from './drill-edit'
import { PhaseNameDialog } from './PhaseNameDialog'
import {
  currentFileAllowsSequentialOverwrite,
  findNextSubgraphExpansionNode,
  sequentialOverwriteConflictForVisibleNode,
  sequentialOverwriteRoutesFromNodeErrors,
} from './sequential-overwrite-routing'
import {
  canvasLayoutSignature,
  layoutCanvasHeightForMode,
  mergeStableLayoutPositions,
  shouldRunInitialViewportFit,
  updateStableLayoutPositionsFromNodeChanges,
} from './canvas-projection'

export interface ChildDetailPatch {
  skillId: string
  workspaceRoot: string | null
  detail: SkillDetail
  revision: number
}

interface GraphCanvasProps {
  skillId: string
  // n2-canvas #14: the parent skill's absolute workspace root (its own skill dir).
  // Used to decide whether a drilled child subgraph is EDITABLE (lives under the
  // editable workspace) or READ-ONLY (a bundled/public skill); see isDrilledChildEditable.
  workspaceRoot?: string | null
  skillDetail?: SkillDetail
  childDetailPatch?: ChildDetailPatch | null
  isLoading?: boolean
  error?: unknown
  selectedNodeId?: string | null
  onNodeSelect?: (node: { id: string, data: SkillGraphNodeData }) => void
  onNodeDeselect?: () => void
  /**
   * Selecting a boundary pseudo-node (Input / Output) carries its identity so
   * the i/o panel can scope to that role (input-boundary / output-boundary),
   * instead of the old behaviour of deselecting to an untyped graph view where
   * clicking Input, Output, or blank were indistinguishable (PM 2026-07-03).
   */
  onBoundarySelect?: (which: 'input' | 'output') => void
  /**
   * Reveal something inside a subgraph's inline topology, driven by clicking a
   * file in the Assets trees. `phaseChain` is the root→leaf chain of phase ids;
   * `nonce` makes repeated requests re-fire.
   * - `select-child`: expand ancestors + select/highlight the leaf child node.
   * - `expand-subgraph`: expand the subgraph's own inline preview and DESELECT
   *   any node (driven by clicking the subgraph's GRAPH.md).
   * Either way the targeted node is centered in the canvas viewport.
   */
  revealRequest?: { phaseChain: string[]; intent: 'select-child' | 'expand-subgraph'; nonce: number } | null
  /**
   * Center the canvas viewport on a root-graph node (at the current zoom),
   * driven by clicking that node's file in the Assets "Skill Files" tree. `nonce`
   * makes repeated requests re-fire. Canvas clicks never set this — selecting a
   * node ON the canvas must not move the viewport.
   */
  focusNodeRequest?: { nodeId: string; nonce: number } | null
  onNodeFileOpen?: (file: FileOpenInput) => void
  onPanelChange?: (panel: PanelKind | null) => void
  // Clicking an already-selected node opens the LAST panel the user had open
  // (recorded by the host), not a hard-coded Properties panel. Falls back to
  // 'properties' when the host does not provide it.
  onOpenSelectedNodePanel?: () => void
  // Clicking empty canvas closes any open side panel AND the file editor(s).
  onCloseEditors?: () => void
  onCreatePhase?: (kind: NewPhaseKind, phaseId?: string, target?: ChildSaveTarget) => Promise<void> | void
  onDeletePhase?: (phaseId: string, target?: ChildSaveTarget) => Promise<void> | void
  // n2-canvas #14: every save handler takes an optional drilled-child `target`. When
  // editing INSIDE a drilled subgraph the canvas passes the child's own identity +
  // SkillDetail + child-refetch so the write/serialize/compile route to the CHILD
  // skill (not the parent). Absent target means parent/root edit, behaviour unchanged.
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
  /** Manual compile errors only. Used for node-anchored authoring confirmations. */
  sequentialOverwriteErrorsByNodeId?: Record<string, CompileError[]>
  /** Full node-error projection (manual compile + lint + data gap). Used only for node badges. */
  compileErrorsByNodeId?: Record<string, CompileError[]>
  goldenStateByNodeId?: Record<string, GoldenNodeState>
  errorMessageByNodeId?: Record<string, string>
  // N5 atom #3 (dirty-downstream-graying): the resume-validity `affected_downstream`
  // node ids. Workspace derives this from the real validity response for the node
  // being resumed from; the canvas grays exactly these nodes (unrelated branches
  // stay normal). Empty/undefined when resume is clean or no node is being resumed.
  dirtyDownstreamNodeIds?: ReadonlySet<string>
  compact?: boolean
  hideMiniMap?: boolean
  onPhaseFileSave?: (args: { path: string; content: string; expectedHash: string }, target?: ChildSaveTarget) => Promise<void> | void
  onPhaseFileRead?: (
    args: { path: string },
    target?: Pick<ChildSaveTarget, 'skillId' | 'workspaceRoot'>,
  ) => Promise<{ content: string; hash?: string | null }> | { content: string; hash?: string | null }
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
  skill: memo(SkillNode),
  globalInput: memo(GlobalInputNode),
  globalOutput: memo(GlobalOutputNode),
  subgraphGroup: memo(SubgraphGroupNode),
}

const edgeTypes = {
  contextEdge: memo(ContextEdge),
  [SUBGRAPH_BRIDGE_EDGE_TYPE]: memo(SubgraphBridgeEdge),
}

const CENTER_NODE_ORIGIN: [number, number] = [0.5, 0.5]
const HIDDEN_INITIAL_VIEWPORT_CLASS = 'opacity-0 pointer-events-none'
const useCanvasLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect
const MINI_MAP_WIDTH = 200
const MINI_MAP_HEIGHT = 120
const MINI_MAP_NODE_WIDTH = 240
const MINI_MAP_NODE_HEIGHT = 64

type SkillMiniMapNodeProps = {
  id: string
  x: number
  y: number
  width: number
  height: number
  className: string
  color?: string
  selected: boolean
  onClick?: (event: MouseEvent, id: string) => void
}

function overwriteConflictKey(conflict: Pick<OverwriteConflict, 'nodeId' | 'fieldName' | 'ancestorNodeId'>): string {
  return `${conflict.nodeId}\0${conflict.fieldName}\0${conflict.ancestorNodeId}`
}

function miniMapNodeColor(node: { type?: string; selected?: boolean }): string {
  if (node.type === 'subgraphGroup') {
    return 'transparent'
  }
  if (node.selected) {
    return 'color-mix(in oklab, var(--studio-canvas-accent) 72%, var(--color-foreground))'
  }
  if (node.type === 'globalInput' || node.type === 'globalOutput') {
    return 'var(--color-muted-foreground)'
  }
  return 'color-mix(in oklab, var(--color-foreground) 78%, var(--studio-canvas-accent) 22%)'
}

function miniMapNodeClassName(node: { type?: string }): string {
  return node.type === 'subgraphGroup' ? 'skill-mini-map-node--group' : 'skill-mini-map-node--phase'
}

function SkillMiniMapNode({ id, x, y, width, height, className, color, selected, onClick }: SkillMiniMapNodeProps) {
  if (className.includes('skill-mini-map-node--group')) {
    return (
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={10}
        fill="transparent"
        stroke="color-mix(in oklab, var(--studio-canvas-accent-muted) 64%, transparent)"
        strokeWidth={4}
        vectorEffect="non-scaling-stroke"
        className={className}
        onClick={onClick ? (event) => onClick(event, id) : undefined}
      />
    )
  }

  const nodeWidth = Math.min(width, MINI_MAP_NODE_WIDTH)
  const nodeHeight = Math.min(height, MINI_MAP_NODE_HEIGHT)
  return (
    <rect
      x={x + (width - nodeWidth) / 2}
      y={y + (height - nodeHeight) / 2}
      width={nodeWidth}
      height={nodeHeight}
      rx={8}
      fill={color}
      opacity={selected ? 0.95 : 0.78}
      className={className}
      onClick={onClick ? (event) => onClick(event, id) : undefined}
    />
  )
}

function SkillMiniMap({ visible }: { visible: boolean }) {
  return (
    <MiniMap
      position="bottom-right"
      className={`react-flow__minimap skill-mini-map ${visible ? 'skill-mini-map--visible' : 'skill-mini-map--hidden'}`}
      style={{ height: MINI_MAP_HEIGHT, width: MINI_MAP_WIDTH }}
      nodeColor={miniMapNodeColor}
      nodeClassName={miniMapNodeClassName}
      nodeComponent={SkillMiniMapNode}
      maskColor="color-mix(in oklab, var(--color-background) 76%, transparent)"
      maskStrokeColor="color-mix(in oklab, var(--studio-canvas-accent-muted) 46%, transparent)"
      maskStrokeWidth={2}
      offsetScale={12}
      pannable
      zoomable
      ariaLabel="Main graph overview"
      aria-hidden={!visible}
    />
  )
}

function SubgraphBridgeInternalsUpdater({ nodes }: { nodes: GraphCanvasNode[] }) {
  const updateNodeInternals = useUpdateNodeInternals()
  const bridgeAnchorNodeIds = useMemo(() => nodes
    .filter((node) => (
      node.type === 'subgraphGroup'
      || (node.type === 'skill' && (node.data as SkillGraphNodeData).isExpanded === true)
    ))
    .map((node) => node.id), [nodes])

  useCanvasLayoutEffect(() => {
    if (bridgeAnchorNodeIds.length === 0) return

    const frame = window.requestAnimationFrame(() => {
      bridgeAnchorNodeIds.forEach((nodeId) => updateNodeInternals(nodeId))
    })
    return () => window.cancelAnimationFrame(frame)
  }, [bridgeAnchorNodeIds, updateNodeInternals])

  return null
}

export function layoutViewportSignature(nodes: GraphCanvasNode[], edges: Edge<ContextEdgeData>[]): string {
  return canvasLayoutSignature(nodes, edges)
}

const SUBGRAPH_PREVIEW_NODE_PREFIX = '__subpreview__::node::'
const ROOT_EXPANSION_SCOPE = '__root__'

function previewNodeParentId(nodeId: string): string | null {
  if (!nodeId.startsWith(SUBGRAPH_PREVIEW_NODE_PREFIX)) {
    return null
  }
  const rest = nodeId.slice(SUBGRAPH_PREVIEW_NODE_PREFIX.length)
  const separator = rest.lastIndexOf('::')
  return separator > 0 ? rest.slice(0, separator) : null
}

function expansionScope(nodeId: string): string {
  return previewNodeParentId(nodeId) ?? ROOT_EXPANSION_SCOPE
}

function isExpansionDescendant(candidateId: string, ancestorId: string): boolean {
  return candidateId.startsWith(`${SUBGRAPH_PREVIEW_NODE_PREFIX}${ancestorId}::`)
}

function deleteExpansionBranch(next: Set<string>, nodeId: string): void {
  for (const candidate of [...next]) {
    if (candidate === nodeId || isExpansionDescendant(candidate, nodeId)) {
      next.delete(candidate)
    }
  }
}

export function nextExpandedSubgraphs(current: ReadonlySet<string>, nodeId: string): Set<string> {
  const next = new Set(current)
  if (next.has(nodeId)) {
    deleteExpansionBranch(next, nodeId)
    return next
  }

  const scope = expansionScope(nodeId)
  for (const expandedId of [...next]) {
    if (expansionScope(expandedId) === scope) {
      deleteExpansionBranch(next, expandedId)
    }
  }
  next.add(nodeId)
  return next
}

function skillNodePhaseId(node: SkillGraphNode): string {
  return typeof node.data.phaseId === 'string' && node.data.phaseId ? node.data.phaseId : node.id
}

function phaseFileRequestForNode(
  node: SkillGraphNode,
  fallbackSkillId: string,
  fallbackWorkspaceRoot: string | null | undefined,
): FileOpenRequest {
  const phaseId = skillNodePhaseId(node)
  return {
    path: node.data.filePath ?? `phases/${phaseId}/${phaseKindFile(node.data)}`,
    skillId: node.data.skillId || fallbackSkillId,
    workspaceRoot: node.data.workspaceRoot ?? fallbackWorkspaceRoot ?? null,
    language: 'markdown',
    saveEnabled: true,
  }
}

function phaseIdFromCanvasNodeId(nodeId: string): string {
  const parentId = previewNodeParentId(nodeId)
  if (!parentId) return nodeId
  const prefix = `${SUBGRAPH_PREVIEW_NODE_PREFIX}${parentId}::`
  return nodeId.startsWith(prefix) ? nodeId.slice(prefix.length) : nodeId
}

interface CanvasScope {
  parentNodeId: string | null
}

function canvasScopeForEndpoints(source: string, target: string): CanvasScope | null {
  const sourceParentId = previewNodeParentId(source)
  const targetParentId = previewNodeParentId(target)
  if (sourceParentId !== targetParentId) {
    return null
  }
  return { parentNodeId: sourceParentId }
}

function localConnectionEndpoints(connection: { source: string; target: string }): { source: string; target: string } {
  return {
    source: phaseIdFromCanvasNodeId(connection.source),
    target: phaseIdFromCanvasNodeId(connection.target),
  }
}

function removeConnectionFromLiveNodes(
  current: GraphCanvasNode[],
  connection: { source: string; target: string },
  localConnection: { source: string; target: string },
): GraphCanvasNode[] {
  let changed = false
  const dependencySource = localConnection.source === INPUT_ID ? 'input' : localConnection.source
  const next = current.map((node) => {
    if (node.type !== 'skill') {
      return node
    }
    if (node.id === connection.target && node.data.dependsOn.includes(dependencySource)) {
      changed = true
      return {
        ...node,
        data: {
          ...node.data,
          dependsOn: node.data.dependsOn.filter((source) => source !== dependencySource),
        },
      }
    }
    if (node.id === connection.source && localConnection.target === OUTPUT_ID && node.data.isOutput === true) {
      changed = true
      return {
        ...node,
        data: {
          ...node.data,
          isOutput: false,
        },
      }
    }
    return node
  })
  return changed ? next : current
}

function addConnectionToLiveNodes(
  current: GraphCanvasNode[],
  connection: { source: string; target: string },
  localConnection: { source: string; target: string },
): GraphCanvasNode[] {
  let changed = false
  const dependencySource = localConnection.source === INPUT_ID ? 'input' : localConnection.source
  const next = current.map((node) => {
    if (node.type !== 'skill') {
      return node
    }
    if (node.id === connection.target && !node.data.dependsOn.includes(dependencySource)) {
      changed = true
      return {
        ...node,
        data: {
          ...node.data,
          dependsOn: [...node.data.dependsOn, dependencySource],
        },
      }
    }
    if (node.id === connection.source && localConnection.target === OUTPUT_ID && node.data.isOutput !== true) {
      changed = true
      return {
        ...node,
        data: {
          ...node.data,
          isOutput: true,
        },
      }
    }
    return node
  })
  return changed ? next : current
}

export function topologyOwnerSkillIdForWorkspace(skillId: string, workspaceRoot?: string | null): string {
  return topLevelSkillIdFromWorkspaceRoot(workspaceRoot) || skillId
}

export function topologyOwnerSkillIdForNode(
  node: SkillGraphNode,
  rootSkillId: string,
  workspaceRoot?: string | null,
): string {
  return (
    topLevelSkillIdFromWorkspaceRoot(node.data.workspaceRoot)
    || topLevelSkillIdFromWorkspaceRoot(workspaceRoot)
    || node.data.topologyOwnerSkillId
    || rootSkillId
  )
}

function isEdgeContextTarget(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest(
    '.react-flow__edge, .react-flow__edgelabel-renderer, [data-edge-context-target="true"]',
  ))
}

interface ContextEdgeHandlers {
  onInspectEdge: NonNullable<ContextEdgeData['onInspectEdge']>
  onEdgeContextMenu: NonNullable<ContextEdgeData['onEdgeContextMenu']>
}

interface ExpandedTopologyEntry {
  path: string
  ownerSkillId?: string
  childSkillId?: string
  view: ExpandedSubgraphView
}

function decorateContextEdge(edge: Edge<ContextEdgeData>, handlers: ContextEdgeHandlers): Edge<ContextEdgeData> {
  const edgeData = edge.data
  const showContextControl = edgeData?.showContextControl !== false
  return {
    ...edge,
    data: {
      ...edgeData,
      hasTraceData: edgeData?.hasTraceData === true,
      contextJson: edgeData?.contextJson,
      sourcePhaseId: edgeData?.sourcePhaseId ?? edge.source,
      targetPhaseId: edgeData?.targetPhaseId ?? edge.target,
      showContextControl,
      onInspectEdge: showContextControl ? handlers.onInspectEdge : undefined,
      onEdgeContextMenu: showContextControl ? handlers.onEdgeContextMenu : undefined,
    },
  }
}

function decorateContextEdges(edges: Edge<ContextEdgeData>[], handlers: ContextEdgeHandlers): Edge<ContextEdgeData>[] {
  return edges.map((edge) => (
    edge.type === 'contextEdge' ? decorateContextEdge(edge, handlers) : edge
  ))
}

function edgeSemanticKey(edge: Edge<ContextEdgeData>): string {
  return JSON.stringify({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle ?? null,
    targetHandle: edge.targetHandle ?? null,
    type: edge.type,
    hasTraceData: edge.data?.hasTraceData === true,
    showContextControl: edge.data?.showContextControl !== false,
    sourcePhaseId: edge.data?.sourcePhaseId ?? edge.source,
    targetPhaseId: edge.data?.targetPhaseId ?? edge.target,
    contextJson: edge.data?.contextJson,
  })
}

function edgeListsSemanticallyEqual(current: Edge<ContextEdgeData>[], next: Edge<ContextEdgeData>[]): boolean {
  if (current.length !== next.length) return false
  const currentKeys = current.map(edgeSemanticKey).sort()
  const nextKeys = next.map(edgeSemanticKey).sort()
  return currentKeys.every((key, index) => key === nextKeys[index])
}

const OPTIONAL_FALSE_NODE_DATA_KEYS = new Set(['isConflictCancelled'])

function semanticJsonValue(value: unknown, key?: string): unknown {
  if (typeof value === 'function') {
    return undefined
  }
  if (key && OPTIONAL_FALSE_NODE_DATA_KEYS.has(key) && value === false) {
    return undefined
  }
  if (Array.isArray(value)) {
    return value.map((item) => semanticJsonValue(item))
  }
  if (value && typeof value === 'object') {
    const sorted: Record<string, unknown> = {}
    for (const [key, nestedValue] of Object.entries(value).sort(([left], [right]) => left.localeCompare(right))) {
      const semanticValue = semanticJsonValue(nestedValue, key)
      if (semanticValue !== undefined) {
        sorted[key] = semanticValue
      }
    }
    return sorted
  }
  return value
}

function nodeSemanticKey(node: GraphCanvasNode): string {
  return JSON.stringify({
    id: node.id,
    type: node.type,
    position: node.position,
    width: node.width ?? null,
    height: node.height ?? null,
    parentId: node.parentId ?? null,
    extent: node.extent ?? null,
    selected: node.selected === true,
    hidden: node.hidden === true,
    data: semanticJsonValue(node.data),
  })
}

function nodeListsSemanticallyEqual(current: GraphCanvasNode[], next: GraphCanvasNode[]): boolean {
  if (current.length !== next.length) return false
  const currentKeys = current.map(nodeSemanticKey).sort()
  const nextKeys = next.map(nodeSemanticKey).sort()
  return currentKeys.every((key, index) => key === nextKeys[index])
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

// Fit-view must frame the graph inside the VISIBLE canvas area, not the full
// container — the side panel / copilot / file editor float ON TOP of the canvas.
// The host already maintains those overlay sizes as CSS custom properties; we
// resolve them to pixels with a throwaway probe so calc()/rem/% are computed by
// the browser. Left/right insets are width-based (rem). The file editor overlay
// is anchored at the TOP of the canvas (`.studio-editor-overlay` is `top-3`) and
// its `min(52%, …)` height is height-relative, so its inset is measured as a
// height and applied to the TOP. Returns zeros when the vars are absent (e.g.
// the compact canvas).
function readCanvasSafeInsets(host: HTMLElement): { left: number; right: number; top: number } {
  if (typeof document === 'undefined') return { left: 0, right: 0, top: 0 }
  const probe = document.createElement('div')
  probe.style.position = 'absolute'
  probe.style.visibility = 'hidden'
  probe.style.pointerEvents = 'none'
  probe.style.top = '0'
  probe.style.left = '0'
  probe.style.width = '0px'
  probe.style.height = '0px'
  host.appendChild(probe)
  try {
    const widthOf = (varName: string): number => {
      probe.style.width = `var(${varName}, 0px)`
      const value = probe.getBoundingClientRect().width
      probe.style.width = '0px'
      return Number.isFinite(value) ? value : 0
    }
    const left = widthOf('--studio-canvas-left-safe-area')
    const right = widthOf('--studio-canvas-right-safe-area')
    probe.style.height = 'var(--studio-canvas-editor-safe-area, 0px)'
    const topRaw = probe.getBoundingClientRect().height
    const top = Number.isFinite(topRaw) ? topRaw : 0
    return { left, right, top }
  } finally {
    host.removeChild(probe)
  }
}

export function GraphCanvas({
  skillId,
  workspaceRoot,
  skillDetail,
  childDetailPatch = null,
  isLoading = false,
  error,
  selectedNodeId,
  onNodeSelect,
  onNodeDeselect,
  onBoundarySelect,
  revealRequest,
  focusNodeRequest,
  onNodeFileOpen,
  onPanelChange,
  onOpenSelectedNodePanel,
  onCloseEditors,
  onCreatePhase,
  onDeletePhase,
  onPersistConnection,
  onDisconnectConnection,
  onReconnectConnection,
  statusByNodeId,
  sequentialOverwriteErrorsByNodeId,
  compileErrorsByNodeId,
  goldenStateByNodeId,
  errorMessageByNodeId,
  dirtyDownstreamNodeIds,
  compact = false,
  hideMiniMap = false,
  onPhaseFileSave,
  onPhaseFileRead,
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
  const workspaceRef = useRef(workspace)
  useEffect(() => {
    workspaceRef.current = workspace
  }, [workspace])
  // n5 atom #14: the dot's static (pre-run) inference derives from the current
  // skill declarations; a ref keeps handleInspectEdge dependency-free.
  const skillDetailRef = useRef(skillDetail)
  useEffect(() => {
    skillDetailRef.current = skillDetail
  }, [skillDetail])
  const [expandedSubgraphs, setExpandedSubgraphs] = useState<Set<string>>(() => new Set())
  // N2 atom #13 (subgraph-inline-preview): resolved child topology per expanded
  // subgraph node, keyed by the parent node id. Drives the canvas-level inline
  // expansion (dashed container + real child nodes/edges). Each entry also stores
  // the source `path` so a path change re-fetches rather than showing a stale child.
  const [expandedTopologies, setExpandedTopologies] = useState<Record<string, ExpandedTopologyEntry>>({})
  const expandedTopologiesRef = useRef(expandedTopologies)
  useEffect(() => {
    expandedTopologiesRef.current = expandedTopologies
  }, [expandedTopologies])
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
  // buildNodes(childSkillId, childDetail, ...) reusing the root edit wiring, so the
  // child is a first-class EDITABLE graph keyed to its own identity, not a read-only
  // topology projection. Null until it resolves (the topology-only view renders meanwhile).
  const [childDetail, setChildDetail] = useState<SkillDetail | null>(null)
  const [childGraphError, setChildGraphError] = useState<string | null>(null)
  const [isChildGraphLoading, setIsChildGraphLoading] = useState(false)
  const [selectionOverride, setSelectionOverride] = useState<{ active: boolean; nodeId: string | null }>({
    active: false,
    nodeId: null,
  })
  const selectionOverrideRef = useRef(selectionOverride)
  const [edgeMenuConnection, setEdgeMenuConnection] = useState<{ source: string; target: string } | null>(null)
  const [nodeMenuPhaseId, setNodeMenuPhaseId] = useState<string | null>(null)
  const [createPhaseKind, setCreatePhaseKind] = useState<NewPhaseKind | null>(null)
  const [canvasHeight, setCanvasHeight] = useState(0)
  const canvasRef = useRef<HTMLElement | null>(null)
  // R4 reconnect: set true the moment a dragged edge endpoint lands on a valid
  // handle (onReconnect). onReconnectEnd reads it to tell "moved to a new node"
  // (reconnect, already handled) apart from "dropped off any handle"
  // (drag-disconnect). Reset on every reconnect start.
  const reconnectLandedRef = useRef(false)
  const reconnectingEdgeRef = useRef<Edge<ContextEdgeData> | null>(null)
  // Drop-flash guard: how many structural graph edits (connect / disconnect /
  // reconnect) have their optimistic mutation applied but their GRAPH.md write
  // still in flight. While > 0 the layout-reconcile effect skips resetting the
  // live nodes/edges from the composed layout. Without this, the synchronous
  // clearStaleCompileProjection re-render (still on the PRE-write skillDetail)
  // recomputes the composed edges from stale data and the reconcile slams the
  // optimistic edge back to its old state until the refetch lands — the flash
  // the user sees on drop. A ref (not state) so begin/end never triggers a
  // render on its own; the effect re-runs off the real data changes.
  const pendingGraphEditsRef = useRef(0)
  // Settle signal for the reconcile effect below: while pending > 0 the effect
  // skips reconciliation, and because the counter is a ref, dropping back to 0
  // triggers no render — so any composedLayout change that landed DURING the
  // edit (e.g. the post-write relint delivering fresh node lint badges before
  // the write promise resolves) would otherwise never reach the rendered nodes.
  const [graphEditsSettledTick, setGraphEditsSettledTick] = useState(0)
  const beginGraphEdit = useCallback(() => {
    pendingGraphEditsRef.current += 1
  }, [])
  const endGraphEdit = useCallback(() => {
    pendingGraphEditsRef.current = Math.max(0, pendingGraphEditsRef.current - 1)
    if (pendingGraphEditsRef.current === 0) {
      setGraphEditsSettledTick((tick) => tick + 1)
    }
  }, [])

  const [warningQueue, setWarningQueue] = useState<OverwriteConflict[]>([])
  const [activeWarningIndex, setActiveWarningIndex] = useState<number>(-1)
  const [cancelledNodeIds, setCancelledNodeIds] = useState<Set<string>>(() => new Set())
  const [suppressedWarningKeys, setSuppressedWarningKeys] = useState<Set<string>>(() => new Set())
  const nodesRef = useRef<GraphCanvasNode[]>([])
  const [isViewportReady, setIsViewportReady] = useState(false)
  const viewportReadyRef = useRef(false)
  const initialViewportFitStartedRef = useRef(false)
  const viewportScopeKeyRef = useRef<string | null>(null)
  const layoutCacheRef = useRef<{
    signature: string
    result: { nodes: GraphCanvasNode[]; edges: Edge<ContextEdgeData>[]; error: CycleDetectedError | null }
  } | null>(null)
  const stableLayoutPositionsRef = useRef<Map<string, GraphCanvasNode['position']>>(new Map())
  // Where the last pane right-click landed, in flow coordinates — used to drop a
  // newly-created node AT the cursor instead of the auto-layout's default slot.
  const lastPaneContextFlowPositionRef = useRef<{ x: number; y: number } | null>(null)
  // Positions to force onto nodes as soon as they appear (keyed by phase id). A
  // created node may not exist in the graph yet when we capture its placement, so
  // we hold the position here until the rebuild surfaces it, then apply + clear.
  const pendingCreatePositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map())
  // Deferred single-click action (open the recorded panel on the SECOND click of
  // an already-selected node). Held in a timeout so a double-click can cancel it
  // and open the editor instead of flashing a panel open.
  const pendingNodeClickActionRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const cancelPendingNodeClickAction = useCallback(() => {
    if (pendingNodeClickActionRef.current) {
      clearTimeout(pendingNodeClickActionRef.current)
      pendingNodeClickActionRef.current = null
    }
  }, [])

  useEffect(() => cancelPendingNodeClickAction, [cancelPendingNodeClickAction])

  const applySelectionOverride = useCallback((nodeId: string | null) => {
    const next = { active: true, nodeId }
    selectionOverrideRef.current = next
    setSelectionOverride(next)
  }, [])

  useEffect(() => {
    const override = selectionOverrideRef.current
    if (
      override.active
      && override.nodeId
      && selectedNodeId
      && phaseIdFromCanvasNodeId(override.nodeId) === selectedNodeId
    ) {
      return
    }
    const next = { active: false, nodeId: null }
    selectionOverrideRef.current = next
    setSelectionOverride(next)
  }, [selectedNodeId])

  const currentActiveSelectedNodeId = useCallback(() => {
    const override = selectionOverrideRef.current
    return override.active ? override.nodeId : selectedNodeId
  }, [selectedNodeId])

  const isCanvasNodeSelected = useCallback((nodeId: string) => (
    currentActiveSelectedNodeId() === nodeId
    || nodesRef.current.some((node) => node.id === nodeId && node.selected)
  ), [currentActiveSelectedNodeId])

  const updateViewportReady = useCallback((ready: boolean) => {
    viewportReadyRef.current = ready
    setIsViewportReady(ready)
  }, [])

  // 2. Sequential overwrite allow/cancel callbacks
  const expandedChildSaveTarget = useCallback((parentNodeId: string): ChildSaveTarget | null => {
    const entry = expandedTopologiesRef.current[parentNodeId]
    if (!entry || entry.view.status !== 'loaded' || !entry.view.detail) return null
    const childSkillId = entry.childSkillId ?? resolveWorkspaceIdentity(`local:${entry.path}`).skillId
    if (!childSkillId) return null
    return {
      skillId: childSkillId,
      workspaceRoot: entry.path,
      detail: entry.view.detail,
      onSettled: async () => undefined,
    }
  }, [])

  const updateExpandedPhaseFile = useCallback((parentNodeId: string, relativePath: string, content: string) => {
    setExpandedTopologies((current) => {
      const entry = current[parentNodeId]
      if (!entry || entry.view.status !== 'loaded' || !entry.view.detail) return current
      return {
        ...current,
        [parentNodeId]: {
          ...entry,
          view: {
            ...entry.view,
            detail: {
              ...entry.view.detail,
              files: {
                ...(entry.view.detail.files ?? {}),
                [relativePath]: content,
              },
            },
          },
        },
      }
    })
  }, [])

  const handleAllowSequentialOverwrite = useCallback(async (nodeId: string, fieldName: string, ancestorNodeId: string) => {
    if (!skillDetail || !onPhaseFileSave) return
    const conflictToClear = warningQueue.find((conflict) => (
      conflict.nodeId === nodeId
      && conflict.fieldName === fieldName
      && conflict.ancestorNodeId === ancestorNodeId
    )) ?? { nodeId, fieldName, ancestorNodeId }
    const conflictKey = overwriteConflictKey(conflictToClear)
    const parentNodeId = previewNodeParentId(nodeId)
    const visibleNode = nodesRef.current.find((node): node is SkillGraphNode => node.type === 'skill' && node.id === nodeId)
    const nodeWorkspaceRoot = visibleNode?.data.workspaceRoot ?? workspaceRoot ?? null
    const isChildFileTarget = Boolean(
      visibleNode
      && (
        visibleNode.data.skillId !== skillId
        || nodeWorkspaceRoot !== (workspaceRoot ?? null)
      ),
    )
    const fallbackDetail = visibleNode?.data.resolvedSkillDetail ?? skillDetail
    const fallbackTarget = visibleNode && isChildFileTarget
      ? {
          skillId: visibleNode.data.skillId || skillId,
          workspaceRoot: nodeWorkspaceRoot,
          detail: fallbackDetail,
          onSettled: async () => undefined,
        } satisfies ChildSaveTarget
      : null
    const target = parentNodeId ? expandedChildSaveTarget(parentNodeId) ?? fallbackTarget : fallbackTarget
    const detail = target?.detail ?? skillDetail
    const phaseId = visibleNode ? skillNodePhaseId(visibleNode) : phaseIdFromCanvasNodeId(nodeId)
    const phase = phaseRefsFromSkillDetail(detail).find((p) => p.id === phaseId)
    const relativePath = visibleNode?.data.filePath ?? (phase ? phaseFilePath(phaseId, phase.mode) : null)
    if (!relativePath) return
    let currentContent: string | undefined
    let currentHash: string | null = null
    if (onPhaseFileRead) {
      try {
        const file = await onPhaseFileRead({ path: relativePath }, target ?? undefined)
        currentContent = file.content
        currentHash = file.hash ?? null
      } catch (readError) {
        toast.error(`Could not read phase file: ${errorMessage(readError)}`)
        return
      }
    }
    if (currentContent === undefined) {
      currentContent = detail.files?.[relativePath]
    }
    if (currentContent === undefined) {
      toast.error(`Phase file is missing: ${relativePath}`)
      return
    }

    const updatedContent = addSequentialOverwriteField(currentContent, fieldName)
    const updatedDetail: SkillDetail = {
      ...detail,
      files: {
        ...(detail.files ?? {}),
        [relativePath]: updatedContent,
      },
    }
    try {
      const hash = currentHash ?? await sha256Hex(currentContent)
      await onPhaseFileSave({
        path: relativePath,
        content: updatedContent,
        expectedHash: hash,
      }, target ?? undefined)
      if (parentNodeId) {
        updateExpandedPhaseFile(parentNodeId, relativePath, updatedContent)
      } else if (isChildFileTarget) {
        setChildDetail((current) => current ? updatedDetail : current)
      }
      if (visibleNode && isChildFileTarget && selectedNodeId === phaseId) {
        onNodeSelect?.({
          id: phaseId,
          data: {
            ...visibleNode.data,
            resolvedSkillDetail: updatedDetail,
          },
        })
      }
      setSuppressedWarningKeys((current) => {
        const next = new Set(current)
        next.add(conflictKey)
        return next
      })
      setCancelledNodeIds((prev) => {
        const next = new Set(prev)
        next.delete(nodeId)
        return next
      })
      setWarningQueue([])
      setActiveWarningIndex(-1)
    } catch (saveError) {
      toast.error(`Could not whitelist sequential overwrite: ${errorMessage(saveError)}`)
    }
  }, [expandedChildSaveTarget, onNodeSelect, onPhaseFileRead, onPhaseFileSave, selectedNodeId, skillDetail, skillId, updateExpandedPhaseFile, warningQueue, workspaceRoot])

  const handleCancelSequentialOverwrite = useCallback((nodeId: string, fieldName: string, ancestorNodeId: string) => {
    setCancelledNodeIds((prev) => {
      const next = new Set(prev)
      next.add(nodeId)
      return next
    })
    setSuppressedWarningKeys((current) => {
      const next = new Set(current)
      next.add(overwriteConflictKey({ nodeId, fieldName, ancestorNodeId }))
      return next
    })
    setWarningQueue([])
    setActiveWarningIndex(-1)
    toast.error('Sequential overwrite still unresolved. Adjust the node or allow overwrite before compiling.')
  }, [])
  const fitViewRef = useRef<(() => Promise<boolean> | boolean | void) | null>(null)
  const reactFlowInstanceRef = useRef<ReactFlowInstance<GraphCanvasNode, Edge<ContextEdgeData>> | null>(null)
  const [canvasLocked, setCanvasLocked] = useState(false)
  const handleZoomIn = useCallback(() => {
    void reactFlowInstanceRef.current?.zoomIn()
  }, [])
  const handleZoomOut = useCallback(() => {
    void reactFlowInstanceRef.current?.zoomOut()
  }, [])
  // Fit the graph into the area NOT covered by the open panel / copilot / editor
  // overlays. Base breathing room plus the live overlay insets, per side.
  const runFitView = useCallback(() => {
    const instance = reactFlowInstanceRef.current
    if (!instance) return
    const host = canvasRef.current
    const insets = host ? readCanvasSafeInsets(host) : { left: 0, right: 0, top: 0 }
    const BASE = 32
    return instance.fitView({
      padding: {
        top: `${insets.top + BASE}px`,
        left: `${insets.left + BASE}px`,
        right: `${insets.right + BASE}px`,
        bottom: `${BASE}px`,
      },
    })
  }, [])
  const handleFitView = useCallback(() => {
    void (fitViewRef.current?.() ?? runFitView())
  }, [runFitView])
  const handleToggleCanvasLock = useCallback(() => {
    setCanvasLocked((locked) => !locked)
  }, [])
  // #3.2: keyboard shortcuts for the high-frequency canvas actions (shown in the
  // right-click menu). Window-level but ignored while typing in a field; zoom/fit
  // honor the canvas lock (the lock toggle itself always works). Modified combos
  // are left to the browser/OS.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      // Require the platform modifier (Ctrl on Win/Linux, Cmd on macOS) so the
      // shortcuts can never fire from plain typing. Ignore other modifier combos.
      if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return
      const target = event.target as HTMLElement | null
      if (target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) return
      switch (event.key) {
        case '=':
        case '+':
          if (canvasLocked) return
          handleZoomIn()
          break
        case '-':
        case '_':
          if (canvasLocked) return
          handleZoomOut()
          break
        case '0':
          if (canvasLocked) return
          handleFitView()
          break
        case 'l':
        case 'L':
          handleToggleCanvasLock()
          break
        default:
          return
      }
      event.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [canvasLocked, handleFitView, handleToggleCanvasLock, handleZoomIn, handleZoomOut])
  const fitInitialViewportOnce = useCallback((hasLayoutNodes: boolean) => {
    const fitView = fitViewRef.current
    if (!shouldRunInitialViewportFit({
      hasLayoutNodes,
      hasFitView: Boolean(fitView),
      initialFitStarted: initialViewportFitStartedRef.current,
      viewportReady: viewportReadyRef.current,
    })) {
      return
    }

    initialViewportFitStartedRef.current = true
    window.requestAnimationFrame(() => {
      let fitResult: Promise<boolean> | boolean | void
      try {
        fitResult = fitView?.()
      } catch {
        updateViewportReady(true)
        return
      }
      void Promise.resolve(fitResult)
        .catch(() => undefined)
        .then(() => {
          updateViewportReady(true)
        })
    })
  }, [updateViewportReady])

  const toggleSubgraph = useCallback((nodeId: string) => {
    setExpandedSubgraphs((current) => nextExpandedSubgraphs(current, nodeId))
  }, [])

  const openNodeFile = useCallback((node: SkillGraphNode) => {
    const openFile = onNodeFileOpen ?? workspaceRef.current?.onFileOpen
    openFile?.(phaseFileRequestForNode(node, skillId, workspaceRoot))
  }, [onNodeFileOpen, skillId, workspaceRoot])

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
  // path. The optimistic-lock hash is taken over the CURRENT (pre-edit) body,
  // the same snapshot the step transforms ran on, so a stale concurrent edit is
  // rejected by the backend hash guard rather than silently overwritten.
  const handleStepsSave = useCallback(
    async (_nodeId: string, filePath: string, currentBody: string, nextBody: string) => {
      if (!onPhaseFileSave) return
      // n2-canvas #14: inside an editable drilled child, route the body save to the
      // child target (read via ref so this stable callback need not depend on the
      // drill state). At root depth the target is null, so parent save is unchanged.
      const childArgs = drilledChildTargetRef.current
        ? ([drilledChildTargetRef.current] as const)
        : ([] as const)
      try {
        const expectedHash = await sha256Hex(currentBody)
        await onPhaseFileSave({ path: filePath, content: nextBody, expectedHash }, ...childArgs)
      } catch (saveError) {
        toast.error(`Could not save steps: ${errorMessage(saveError)}`)
      }
    },
    [onPhaseFileSave],
  )

  const handleExpandedPreviewStepsSave = useCallback(
    async (_nodeId: string, filePath: string, currentBody: string, nextBody: string, parentNodeId: string) => {
      if (!onPhaseFileSave) return
      const target = expandedChildSaveTarget(parentNodeId)
      if (!target) {
        toast.error('Could not save steps: child subgraph is not ready')
        return
      }
      try {
        const expectedHash = await sha256Hex(currentBody)
        await onPhaseFileSave({ path: filePath, content: nextBody, expectedHash }, target)
        updateExpandedPhaseFile(parentNodeId, filePath, nextBody)
      } catch (saveError) {
        toast.error(`Could not save steps: ${errorMessage(saveError)}`)
      }
    },
    [expandedChildSaveTarget, onPhaseFileSave, updateExpandedPhaseFile],
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
  const viewportScopeKey = `${skillId}\0${drilledPath ?? ''}`
  const topologyRootSkillId = useMemo(
    () => topologyOwnerSkillIdForWorkspace(skillId, workspaceRoot),
    [skillId, workspaceRoot],
  )
  useCanvasLayoutEffect(() => {
    if (viewportScopeKeyRef.current === null) {
      viewportScopeKeyRef.current = viewportScopeKey
      return
    }
    if (viewportScopeKeyRef.current === viewportScopeKey) {
      return
    }
    viewportScopeKeyRef.current = viewportScopeKey
    layoutCacheRef.current = null
    stableLayoutPositionsRef.current = new Map()
    initialViewportFitStartedRef.current = false
    updateViewportReady(false)
  }, [updateViewportReady, viewportScopeKey])

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
      const topology = await getChildGraphTopology(topologyRootSkillId, path)
      if (signal.cancelled) return
      setChildGraph(topology)
      const childSkillId = resolveWorkspaceIdentity(`local:${topology.path}`).skillId
      if (topology.detail) {
        setChildDetail(topology.detail)
      } else if (childSkillId) {
        try {
          const detail = await getSkillDetail(childSkillId)
          if (signal.cancelled) return
          setChildDetail(detail)
        } catch (detailError) {
          // The child topology rendered; its full detail (needed for in-place
          // editing) failed to load. Keep the read-only topology view and warn;
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
  }, [topologyRootSkillId])

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
  // rolled-back / committed child state; the child analogue of mutateSkillDetail.
  const refetchChildGraph = useCallback(async () => {
    if (!drilledPath) return
    const signal = { cancelled: false }
    childLoadSignalRef.current = signal
    await loadChildGraph(drilledPath, signal)
  }, [drilledPath, loadChildGraph])
  const safeStatusByNodeId = useMemo(() => statusByNodeId ?? {}, [statusByNodeId])
  const safeCompileErrorsByNodeId = useMemo(() => compileErrorsByNodeId ?? {}, [compileErrorsByNodeId])
  const safeSequentialOverwriteErrorsByNodeId = useMemo(
    () => sequentialOverwriteErrorsByNodeId ?? {},
    [sequentialOverwriteErrorsByNodeId],
  )
  const sequentialOverwriteRoutes = useMemo(
    () => sequentialOverwriteRoutesFromNodeErrors(safeSequentialOverwriteErrorsByNodeId, workspaceRoot ?? null),
    [safeSequentialOverwriteErrorsByNodeId, workspaceRoot],
  )
  const safeGoldenStateByNodeId = useMemo(() => goldenStateByNodeId ?? {}, [goldenStateByNodeId])
  const safeErrorMessageByNodeId = useMemo(() => errorMessageByNodeId ?? {}, [errorMessageByNodeId])
  const safeDirtyDownstreamNodeIds = useMemo(
    () => dirtyDownstreamNodeIds ?? new Set<string>(),
    [dirtyDownstreamNodeIds],
  )
  const compactRatio = compact && canvasHeight > 0 && canvasHeight < 500 ? 0.2 : 0

  useCanvasLayoutEffect(() => {
    const element = canvasRef.current
    if (!element) return
    const updateHeight = () => setCanvasHeight(element.getBoundingClientRect().height)
    updateHeight()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(updateHeight)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const isDrilled = drilledPath !== null

  // n2-canvas #14: the drilled child's own save identity, derived purely on the FE
  // from the backend-resolved absolute child path (childGraph.path), the SAME
  // resolution the removed project-switch escape hatch used. Null at root depth.
  const drilledChildIdentity = useMemo(
    () => (isDrilled && childGraph ? resolveWorkspaceIdentity(`local:${childGraph.path}`) : null),
    [isDrilled, childGraph],
  )
  // n2-canvas #14 (PM decision): a drilled child that resolves to a READ-ONLY
  // bundled/public skill (outside the editable workspace) is NOT editable in place
  // block, don't auto-fork, don't silently mutate. Determined up front, path-based.
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
  useEffect(() => {
    if (!childDetailPatch) return
    const patchedPhaseRefs = phaseRefsFromSkillDetail(childDetailPatch.detail)
    const patchedPhaseIds = patchedPhaseRefs.map((phase) => phase.id)
    const patchedGraphTopology = childDetailPatch.detail.graph_topology
    setExpandedTopologies((current) => {
      let changed = false
      const next: typeof current = {}
      for (const [nodeId, entry] of Object.entries(current)) {
        const entrySkillId = entry.childSkillId ?? resolveWorkspaceIdentity(`local:${entry.path}`).skillId
        const entryWorkspaceRoot = entry.path
        if (
          entry.view.status === 'loaded'
          && entrySkillId === childDetailPatch.skillId
          && entryWorkspaceRoot === childDetailPatch.workspaceRoot
        ) {
          next[nodeId] = {
            ...entry,
            view: {
              ...entry.view,
              phases: patchedPhaseIds.length > 0 ? patchedPhaseIds : entry.view.phases,
              graphTopology: patchedGraphTopology ?? entry.view.graphTopology,
              detail: childDetailPatch.detail,
            },
          }
          changed = true
        } else {
          next[nodeId] = entry
        }
      }
      return changed ? next : current
    })
    const drilledTarget = drilledChildTargetRef.current
    if (
      drilledTarget
      && drilledTarget.skillId === childDetailPatch.skillId
      && drilledTarget.workspaceRoot === childDetailPatch.workspaceRoot
    ) {
      setChildDetail(childDetailPatch.detail)
    }
  }, [childDetailPatch])
  // n2-canvas #14: connect/reconnect affordances are live when the canvas is the
  // main (non-compact) editor AND, if drilled, the child is editable (not a
  // read-only bundled/public subgraph). A read-only drilled child renders but
  // cannot start a structure edit (the PM read-only block).
  const canEditCanvas = !compact && !(isDrilled && isDrilledChildReadOnly)

  // N2 atom #15: the inline L3 step-editor inputs threaded into AGENT nodes.
  // compact = read-only projection: withhold the in-node edit callbacks so the
  // "Edit steps" affordance never renders on the mini-canvas (canEditSteps keys
  // on onToggleSteps being a function). Only the read-only dirty-downstream
  // graying is kept; editing the body stays on the main canvas.
  const agentStepsInputs = useMemo(
    () => ({
      expandedSteps: compact ? undefined : expandedSteps,
      onToggleSteps: compact ? undefined : toggleSteps,
      onStepsSave: compact ? undefined : handleStepsSave,
      dirtyDownstreamNodeIds: safeDirtyDownstreamNodeIds,
    }),
    [compact, expandedSteps, toggleSteps, handleStepsSave, safeDirtyDownstreamNodeIds],
  )
  const rawNodes = useMemo<GraphCanvasNode[]>(() => {
    // R9 / n2-canvas #14: when focused into a child graph, render its real phases.
    // Status overlays (which key on ROOT phase ids) are dropped at depth.
    if (isDrilled) {
      if (!childGraph) return []
      // The drilled nodes key to the CHILD's own skillId so edits/file opens resolve
      // against the child, not the parent. Edit affordances are withheld for a
      // read-only child (empty agentSteps), realising the PM read-only block.
      const childNodeSkillId = drilledChildIdentity?.skillId ?? skillId
      const childAgentSteps = isDrilledChildReadOnly ? {} : agentStepsInputs
      // Option A: once the child's full path-resolved SkillDetail loads, render it
      // as a first-class editable graph with buildNodes (reusing the root edit
      // wiring). Until then, render the topology-only projection.
      if (childDetail && !isDrilledChildReadOnly) {
        return buildNodes(childNodeSkillId, childDetail, expandedSubgraphs, toggleSubgraph, {}, {}, {}, {}, childAgentSteps, childGraph.path)
          .map((node) => node.type === 'skill'
            ? { ...node, data: { ...node.data, resolvedSkillDetail: childDetail } }
            : node)
      }
      return buildNodesFromTopology(childNodeSkillId, childGraph.phases, childGraph.graph_topology, {}, childAgentSteps, childGraph.path)
    }
    if (isLoading && !skillDetail) return []
    return buildNodes(skillId, skillDetail, expandedSubgraphs, toggleSubgraph, safeStatusByNodeId, safeCompileErrorsByNodeId, safeGoldenStateByNodeId, safeErrorMessageByNodeId, agentStepsInputs, workspaceRoot ?? null)
  }, [agentStepsInputs, childDetail, childGraph, drilledChildIdentity, expandedSubgraphs, isDrilled, isDrilledChildReadOnly, isLoading, safeStatusByNodeId, safeCompileErrorsByNodeId, safeGoldenStateByNodeId, safeErrorMessageByNodeId, skillDetail, skillId, toggleSubgraph, workspaceRoot])
  const phaseNodes = useMemo(
    () => rawNodes.filter((node): node is SkillGraphNode => node.type === 'skill'),
    [rawNodes],
  )
  // Trace events drive hasTraceData: an edge lights up only when the active run
  // actually dispatched data across it (matching input_dispatch event).
  const traceEvents = workspace?.traceEvents
  const openEdgeContextMenu = useCallback((
    _event: MouseEvent,
    connection: { source: string; target: string },
  ) => {
    setEdgeMenuConnection(connection)
  }, [])
  const handleInspectEdge = useCallback<NonNullable<ContextEdgeData['onInspectEdge']>>(({ id, source, target, contextJson }) => {
    const currentWorkspace = workspaceRef.current
    if (!currentWorkspace?.setSelectedEdge || !currentWorkspace?.onPanelChange) {
      return
    }
    // Runtime transition first (real dispatched blackboard); before any run
    // exists fall back to the static declared-fields inference (n5 atom #14).
    const resolvedContextJson = contextJson === undefined
      ? edgeContextFromEvents(currentWorkspace.traceEvents ?? [], source, target)
        ?? staticEdgeInference(skillDetailRef.current, source, target)
        ?? undefined
      : contextJson as EdgeContextJson
    currentWorkspace.setSelectedEdge({
      id,
      source,
      target,
      contextJson: resolvedContextJson,
    })
    // D14: the dot is trace-owned. Route to the timeline (trace) panel, not
    // Properties, which no longer renders edge JSON.
    currentWorkspace.onPanelChange('timeline')
  }, [])
  const edgeHandlers = useMemo<ContextEdgeHandlers>(
    () => ({
      onInspectEdge: handleInspectEdge,
      onEdgeContextMenu: openEdgeContextMenu,
    }),
    [handleInspectEdge, openEdgeContextMenu],
  )
  // No nodes at all (e.g. drilled child still loading) means no edges, so we never
  // emit a phantom INPUT鈫扥UTPUT edge against a node-less canvas.
  const topologyEdges = useMemo(
    () => (rawNodes.length === 0 ? [] : buildEdges(phaseNodes)),
    [phaseNodes, rawNodes.length],
  )
  const rawEdges = useMemo(
    () => (rawNodes.length === 0 ? [] : buildEdges(phaseNodes, traceEvents)),
    [phaseNodes, rawNodes.length, traceEvents],
  )
  const layoutCanvasHeight = layoutCanvasHeightForMode(canvasHeight, compactRatio)
  const layoutSignature = useMemo(
    () => canvasLayoutSignature(rawNodes, [], { canvasHeight: layoutCanvasHeight, compactRatio }),
    [compactRatio, layoutCanvasHeight, rawNodes],
  )
  const layoutResult = useMemo((): { nodes: GraphCanvasNode[]; edges: Edge<ContextEdgeData>[]; error: CycleDetectedError | null } => {
    const cached = layoutCacheRef.current
    if (cached?.signature === layoutSignature) {
      return cached.result
    }
    let result: { nodes: GraphCanvasNode[]; edges: Edge<ContextEdgeData>[]; error: CycleDetectedError | null }
    try {
      result = {
        ...getAutoLayoutedElements(rawNodes, topologyEdges, { canvasHeight: layoutCanvasHeight, compactRatio }),
        error: null,
      }
    } catch (layoutError) {
      if (layoutError instanceof CycleDetectedError) {
        result = { nodes: rawNodes, edges: topologyEdges, error: layoutError }
      } else {
        throw layoutError
      }
    }
    layoutCacheRef.current = { signature: layoutSignature, result }
    return result
  }, [compactRatio, layoutCanvasHeight, layoutSignature, rawNodes, topologyEdges])
  const baseLayout = useMemo(() => {
    const stableLayout = mergeStableLayoutPositions(rawNodes, layoutResult.nodes, stableLayoutPositionsRef.current)
    // Drop right-click-created nodes at the captured cursor position the moment
    // they materialize, overriding the auto-layout slot. Consumed once applied.
    const pending = pendingCreatePositionsRef.current
    const positionedNodes = pending.size === 0 ? stableLayout.nodes : stableLayout.nodes.map((node) => {
      const placement = pending.get(node.id)
      if (!placement) return node
      pending.delete(node.id)
      stableLayout.positions.set(node.id, placement)
      return { ...node, position: placement }
    })
    stableLayoutPositionsRef.current = stableLayout.positions
    return {
      nodes: positionedNodes,
      edges: rawEdges,
    }
  }, [layoutResult.nodes, rawEdges, rawNodes])
  // N2 atom #13 (subgraph-inline-preview): expanding a subgraph should only
  // decide whether its child topology is present in the same React Flow graph.
  // The expanded child nodes/edges are fed into useNodesState/useEdgesState with
  // the root graph, so handles, measurement, and edge routing all use the normal
  // canvas pipeline. The base layout signature is visible-node based: editing
  // dependency edges redraws lines, but it must not rerun dagre or move nodes.
  const subgraphExpansion = useMemo(() => {
    // Inline subgraph expansion works the SAME at root depth and inside a drilled
    // child graph — expanding a subgraph node previews its topology beside it
    // either way (no isDrilled short-circuit).
    const nodes: GraphCanvasNode[] = []
    const edges: Edge<ContextEdgeData>[] = []
    const processed = new Set<string>()

    for (let depth = 0; depth <= expandedSubgraphs.size; depth += 1) {
      const availableNodes = [...baseLayout.nodes, ...nodes]
      const requests: SubgraphExpansionRequest[] = []
      for (const node of availableNodes) {
        if (node.type !== 'skill' || !expandedSubgraphs.has(node.id) || processed.has(node.id)) continue
        processed.add(node.id)
        const path = resolveSubgraphPath(node.data.subgraphPath, node.data.workspaceRoot)
        if (!path) {
          // No usable child path: there is nothing to fetch, so expand straight to the
          // inline recovery state (F4 "unresolved path shows recovery state"). Since
          // #199 the backend resolves a declared relative/absolute path to absolute, so
          // this branch is reached only when SUBGRAPH.md declares no path at all. This
          // is why the "+" now appears on these nodes too.
          requests.push({
            parentNodeId: node.id,
            parentLabel: node.data.label,
            path: node.data.subgraphPath ?? '',
            view: { status: 'error', message: 'This subgraph phase does not declare a usable path in SUBGRAPH.md.' },
          })
          continue
        }
        const entry = expandedTopologies[node.id]
        const view: ExpandedSubgraphView = entry && entry.path === path ? entry.view : { status: 'loading' }
        const childIdentity = entry?.childSkillId ? null : resolveWorkspaceIdentity(`local:${path}`)
        requests.push({
          parentNodeId: node.id,
          parentLabel: node.data.label,
          path,
          topologyOwnerSkillId: topologyOwnerSkillIdForNode(node, topologyRootSkillId, workspaceRoot),
          childSkillId: entry?.childSkillId ?? childIdentity?.skillId ?? undefined,
          view,
        })
      }
      if (requests.length === 0) break
      const parentNodes = positionedParentNodes(availableNodes)
      const partial = buildSubgraphExpansion(parentNodes, requests, {
        expandedSubgraphs,
        onToggleSubgraph: toggleSubgraph,
        expandedSteps,
        onToggleSteps: toggleSteps,
        onStepsSave: handleExpandedPreviewStepsSave,
      })
      // The expanded subgraph board carries an "open child canvas" button
      // (drill-in). Double-clicking the subgraph node now opens its file instead.
      nodes.push(...partial.nodes.map((node) => (
        node.type === 'subgraphGroup'
          ? { ...node, data: { ...node.data, onOpenCanvas: drillInto } }
          : node
      )))
      edges.push(...partial.edges)
    }

    return { nodes, edges }
  }, [
    baseLayout.nodes,
    drillInto,
    expandedSteps,
    expandedSubgraphs,
    expandedTopologies,
    handleExpandedPreviewStepsSave,
    topologyRootSkillId,
    toggleSteps,
    toggleSubgraph,
    workspaceRoot,
  ])
  const composedLayout = useMemo(
    () => {
      const composedNodes = subgraphExpansion.nodes.length > 0
        ? [...baseLayout.nodes, ...subgraphExpansion.nodes]
        : baseLayout.nodes
      return {
        nodes: composedNodes,
        edges: subgraphExpansion.edges.length > 0
          ? [...baseLayout.edges, ...subgraphExpansion.edges]
          : baseLayout.edges,
      }
    },
    [
      baseLayout.edges,
      baseLayout.nodes,
      subgraphExpansion.edges,
      subgraphExpansion.nodes,
    ],
  )
  const routedSequentialOverwriteConflicts = useMemo(() => {
    const conflicts: OverwriteConflict[] = []
    for (const route of sequentialOverwriteRoutes) {
      const conflict = sequentialOverwriteConflictForVisibleNode(composedLayout.nodes, route)
      if (conflict) conflicts.push(conflict)
    }
    return conflicts
  }, [composedLayout.nodes, sequentialOverwriteRoutes])
  const allSequentialOverwriteConflicts = useMemo(() => {
    const conflicts: OverwriteConflict[] = []
    const seen = new Set<string>()
    for (const conflict of routedSequentialOverwriteConflicts) {
      if (currentFileAllowsSequentialOverwrite(composedLayout.nodes, skillDetail, conflict)) continue
      const key = overwriteConflictKey(conflict)
      if (suppressedWarningKeys.has(key)) continue
      if (seen.has(key)) continue
      seen.add(key)
      conflicts.push(conflict)
    }
    return conflicts
  }, [composedLayout.nodes, routedSequentialOverwriteConflicts, skillDetail, suppressedWarningKeys])
  useEffect(() => {
    setWarningQueue(allSequentialOverwriteConflicts)
    setActiveWarningIndex(allSequentialOverwriteConflicts.length > 0 ? 0 : -1)
  }, [allSequentialOverwriteConflicts])
  useEffect(() => {
    if (isDrilled || sequentialOverwriteRoutes.length === 0) return
    const nodeId = findNextSubgraphExpansionNode(composedLayout.nodes, expandedSubgraphs, sequentialOverwriteRoutes)
    if (!nodeId) return
    setExpandedSubgraphs((current) => (
      current.has(nodeId) ? current : nextExpandedSubgraphs(current, nodeId)
    ))
  }, [composedLayout.nodes, expandedSubgraphs, isDrilled, sequentialOverwriteRoutes])
  // N2 atom #13 (subgraph-inline-preview): resolve child topology for every
  // expanded subgraph node currently present in the composed React Flow graph.
  // The backend boundary resolver must stay pinned to the root/opened skill for
  // embedded child roots, otherwise a same-name global skill can be picked as the
  // parent boundary and reject a valid nested child path.
  const expandedPathPairs = useMemo(() => {
    return composedLayout.nodes
      .filter((node): node is SkillGraphNode => node.type === 'skill' && expandedSubgraphs.has(node.id))
      .map((node) => ({
        id: node.id,
        path: resolveSubgraphPath(node.data.subgraphPath, node.data.workspaceRoot),
        ownerSkillId: topologyOwnerSkillIdForNode(node, topologyRootSkillId, workspaceRoot),
      }))
      .filter((pair): pair is { id: string; path: string; ownerSkillId: string } => Boolean(pair.path))
      .sort((a, b) => a.id.localeCompare(b.id))
  }, [composedLayout.nodes, expandedSubgraphs, topologyRootSkillId, workspaceRoot])
  const expandedPathKey = useMemo(
    () => expandedPathPairs.map((pair) => `${pair.id}\0${pair.ownerSkillId}\0${pair.path}`).join('|'),
    [expandedPathPairs],
  )
  const expandedPathPairsRef = useRef(expandedPathPairs)
  useEffect(() => {
    expandedPathPairsRef.current = expandedPathPairs
  }, [expandedPathPairs])
  useEffect(() => {
    const targets = expandedPathPairsRef.current
    const allowed = new Set(targets.map((target) => target.id))
    // Drop resolved entries for subgraphs that collapsed / are no longer expanded.
    setExpandedTopologies((current) => {
      let changed = false
      const next: typeof current = {}
      for (const [id, entry] of Object.entries(current)) {
        if (allowed.has(id)) next[id] = entry
        else changed = true
      }
      return changed ? next : current
    })
    let cancelled = false
    for (const target of targets) {
      const existing = expandedTopologiesRef.current[target.id]
      // Already resolved for this exact path; keep it. A 'loading' entry is
      // re-fetched because its prior in-flight request belonged to a now-cancelled
      // effect closure (the key changed), so it would otherwise hang.
      if (
        existing
        && existing.path === target.path
        && existing.ownerSkillId === target.ownerSkillId
        && existing.view.status !== 'loading'
      ) {
        continue
      }
      setExpandedTopologies((current) => ({
        ...current,
        [target.id]: { path: target.path, ownerSkillId: target.ownerSkillId, view: { status: 'loading' } },
      }))
      getChildGraphTopology(target.ownerSkillId, target.path)
        .then(async (topology) => {
          if (cancelled) return
          const childIdentity = resolveWorkspaceIdentity(`local:${topology.path}`)
          const childSkillId = childIdentity.skillId ?? undefined
          let detail: SkillDetail | undefined = topology.detail ?? undefined
          if (!detail && childSkillId) {
            try {
              detail = await getSkillDetail(childSkillId)
            } catch (detailError) {
              if (cancelled) return
              console.warn('inline subgraph child detail failed to load; falling back to topology-only nodes', detailError)
            }
          }
          if (cancelled) return
          setExpandedTopologies((current) => {
            if (current[target.id]?.path !== target.path) return current
            return {
              ...current,
              [target.id]: {
                path: target.path,
                ownerSkillId: target.ownerSkillId,
                childSkillId,
                view: {
                  status: 'loaded',
                  name: topology.name,
                  phases: topology.phases,
                  graphTopology: topology.graph_topology,
                  detail,
                },
              },
            }
          })
        })
        .catch((error: unknown) => {
          if (cancelled) return
          setExpandedTopologies((current) => {
            if (current[target.id]?.path !== target.path) return current
            return {
              ...current,
              [target.id]: {
                path: target.path,
                ownerSkillId: target.ownerSkillId,
                view: { status: 'error', message: childGraphErrorMessage(error, target.path) },
              },
            }
          })
        })
    }
    return () => {
      cancelled = true
    }
  }, [expandedPathKey])
  const decoratedComposedEdges = useMemo(
    () => decorateContextEdges(composedLayout.edges, edgeHandlers),
    [composedLayout.edges, edgeHandlers],
  )
  const [nodes, setNodes, onNodesChange] = useNodesState<GraphCanvasNode>(composedLayout.nodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(decoratedComposedEdges)
  nodesRef.current = nodes

  const syncCanvasSelection = useCallback((nodeId: string | null) => {
    applySelectionOverride(nodeId)
    setNodes((currentNodes) => {
      let changed = false
      const nextNodes = currentNodes.map((node) => {
        const selected = node.id === nodeId
        if (node.selected === selected) {
          return node
        }
        changed = true
        return { ...node, selected }
      })
      return changed ? nextNodes : currentNodes
    })
  }, [applySelectionOverride, setNodes])

  // Bring a node into the visible canvas, accounting for the panel/copilot/editor
  // overlay insets (the editor is anchored at the canvas top, so its height is the
  // top inset — focus never lands under it). Used only for Assets-driven reveals;
  // selecting a node ON the canvas must leave the viewport untouched.
  //  - default (pan-only): keep the current zoom, just center the node. For
  //    selecting a specific node, where a zoom jump would be jarring.
  //  - fit: zoom OUT if needed so a whole panel fits, but never zoom IN past
  //    current. For expanding a subgraph, where the goal is to see the full group.
  const focusNodeOnCanvas = useCallback((nodeId: string, opts?: { fit?: boolean }): boolean => {
    const instance = reactFlowInstanceRef.current
    if (!instance || !instance.getNode(nodeId)) return false
    const zoom = instance.getZoom()
    const host = canvasRef.current
    const insets = host ? readCanvasSafeInsets(host) : { left: 0, right: 0, top: 0 }
    const BASE = 48
    void instance.fitView({
      nodes: [{ id: nodeId }],
      duration: 400,
      maxZoom: zoom,
      ...(opts?.fit ? {} : { minZoom: zoom }),
      padding: {
        top: `${insets.top + BASE}px`,
        left: `${insets.left + BASE}px`,
        right: `${insets.right + BASE}px`,
        bottom: `${BASE}px`,
      },
    })
    return true
  }, [])

  // Reveal (Assets trees → canvas): two intents, both retried as the live `nodes`
  // update because nested preview nodes only exist after their parent expands +
  // the child topology resolves asynchronously.
  //  - select-child: expand ancestors, then select+highlight the leaf child node.
  //  - expand-subgraph: expand the subgraph's own inline preview, deselecting any
  //    node (clicking a subgraph's GRAPH.md).
  const pendingChildSelectRef = useRef<{ expandIds: string[]; selectId: string } | null>(null)
  const pendingExpandRef = useRef<string[] | null>(null)
  // `onNodeSelect`/`onNodeDeselect` are NOT memoized by the parent (new ref every
  // render). Read them (and syncCanvasSelection) through refs so the try* helpers
  // are STABLE callbacks — otherwise the reveal effects would re-run every render,
  // perpetually re-arm + re-select, and setState in an infinite loop.
  const onNodeSelectRef = useRef(onNodeSelect)
  onNodeSelectRef.current = onNodeSelect
  const onNodeDeselectRef = useRef(onNodeDeselect)
  onNodeDeselectRef.current = onNodeDeselect
  const syncCanvasSelectionRef = useRef(syncCanvasSelection)
  syncCanvasSelectionRef.current = syncCanvasSelection
  const trySelectPendingChild = useCallback(() => {
    const pending = pendingChildSelectRef.current
    if (!pending) return
    // Expand each subgraph ancestor as it surfaces. A nested preview node only
    // exists once its parent is expanded AND the child topology resolves, so we
    // walk the chain progressively across `nodes` updates (deeper levels appear
    // on later passes). Each step only flips state when it actually changes
    // something, so this can never feed an infinite loop.
    for (const id of pending.expandIds) {
      const exists = nodesRef.current.some((candidate) => candidate.type === 'skill' && candidate.id === id)
      if (exists) {
        setExpandedSubgraphs((current) => (current.has(id) ? current : nextExpandedSubgraphs(current, id)))
      }
    }
    const node = nodesRef.current.find(
      (candidate): candidate is SkillGraphNode => candidate.type === 'skill' && candidate.id === pending.selectId,
    )
    if (!node) return
    pendingChildSelectRef.current = null
    syncCanvasSelectionRef.current(pending.selectId)
    onNodeSelectRef.current?.({ id: skillNodePhaseId(node), data: node.data })
    focusNodeOnCanvas(pending.selectId)
  }, [focusNodeOnCanvas])
  const tryExpandPending = useCallback(() => {
    const ids = pendingExpandRef.current
    if (!ids || ids.length === 0) return
    for (const id of ids) {
      const exists = nodesRef.current.some((candidate) => candidate.type === 'skill' && candidate.id === id)
      if (exists) {
        setExpandedSubgraphs((current) => (current.has(id) ? current : nextExpandedSubgraphs(current, id)))
      }
    }
    // Focus the expanded GROUP container (the child topology box), not the small
    // subgraph chip — the chip sits to the LEFT of the group, so centering on it
    // would leave the topology off to the right. The group node only exists once
    // the subgraph is expanded + its layout composes, so wait for it (retried on
    // each `nodes` update). Loading/error states also render a group node.
    const groupId = subgraphGroupNodeId(ids[ids.length - 1])
    const group = nodesRef.current.find((candidate) => candidate.id === groupId)
    if (!group) return // expansion / deeper level still resolving; retry next update
    // Wait until the child topology has LOADED — while loading the group is a tiny
    // 300×132 placeholder, so centering on it then would frame the header, not the
    // full panel. Once loaded (or errored) it has its real size; fit the WHOLE
    // group centered. Keep retrying on each `nodes` update until then.
    if ((group.data as { status?: string }).status === 'loading') return
    if (focusNodeOnCanvas(groupId, { fit: true })) {
      pendingExpandRef.current = null
    }
  }, [focusNodeOnCanvas])
  // Arm pending state ONLY when a new request (nonce) arrives — never on a plain
  // re-render — so the reveal can't feed back into re-arming.
  const handledRevealNonceRef = useRef(0)
  useEffect(() => {
    if (!revealRequest || revealRequest.nonce === handledRevealNonceRef.current) return
    handledRevealNonceRef.current = revealRequest.nonce
    if (revealRequest.intent === 'expand-subgraph') {
      const ids = subgraphNodeIdChain(revealRequest.phaseChain)
      if (ids.length === 0) return
      pendingChildSelectRef.current = null
      pendingExpandRef.current = ids
      // Deselect any node — opening a subgraph's GRAPH.md is a graph-level action.
      syncCanvasSelectionRef.current(null)
      onNodeDeselectRef.current?.()
      tryExpandPending()
      return
    }
    const resolved = subgraphRevealNodeIds(revealRequest.phaseChain)
    if (!resolved) return
    pendingExpandRef.current = null
    pendingChildSelectRef.current = resolved
    // Already-expanded case: ancestors/preview node may exist right now.
    trySelectPendingChild()
  }, [revealRequest, trySelectPendingChild, tryExpandPending])
  useEffect(() => {
    // Retry as expansion + child topology resolve surface the target node. Once
    // handled, pending is cleared so this is a no-op until the next request.
    trySelectPendingChild()
    tryExpandPending()
  }, [nodes, trySelectPendingChild, tryExpandPending])
  // Root-graph node focus (Assets "Skill Files" → canvas): pan to the node a file
  // click selected, without touching selection (the parent owns that).
  const handledFocusNonceRef = useRef(0)
  useEffect(() => {
    if (!focusNodeRequest || focusNodeRequest.nonce === handledFocusNonceRef.current) return
    handledFocusNonceRef.current = focusNodeRequest.nonce
    focusNodeOnCanvas(focusNodeRequest.nodeId)
  }, [focusNodeRequest, focusNodeOnCanvas])

  // Selection is OWNED by the app (selectedNodeId + override), never by React
  // Flow's internal selection. `stampSelection` flips ONLY the `selected` flag
  // from the active id, read through a ref so the layout-rebuild effect can apply
  // it WITHOUT depending on selection — otherwise every select (e.g. starting to
  // drag another node) would re-run that effect and snap dragged nodes back to
  // their stale composed-layout positions.
  const activeSelectionRef = useRef<string | null>(null)
  const stampSelection = useCallback((list: GraphCanvasNode[]): GraphCanvasNode[] => {
    const activeId = activeSelectionRef.current
    let changed = false
    const next = list.map((node) => {
      if (node.type === 'subgraphGroup') return node
      const selected = node.id === activeId
      if (node.selected === selected) return node
      changed = true
      return { ...node, selected }
    })
    return changed ? next : list
  }, [])

  // Re-apply selection to the LIVE nodes whenever the active selection changes.
  // Only `selected` is touched, so any in-progress drag positions are preserved.
  useEffect(() => {
    activeSelectionRef.current = currentActiveSelectedNodeId() ?? null
    setNodes((current) => stampSelection(current))
  }, [currentActiveSelectedNodeId, setNodes, stampSelection])

  const handleNodesChange = useCallback((changes: NodeChange<GraphCanvasNode>[]) => {
    // Drop React Flow's own selection changes — the app is the single source of
    // truth for selection (so the highlight can never drift from selectedNodeId).
    const nonSelectChanges = changes.filter((change) => change.type !== 'select')
    if (nonSelectChanges.length > 0) {
      onNodesChange(nonSelectChanges)
    }
    stableLayoutPositionsRef.current = updateStableLayoutPositionsFromNodeChanges(
      stableLayoutPositionsRef.current,
      changes,
    )
  }, [onNodesChange])

  const hasLayoutNodes = baseLayout.nodes.length > 0

  useCanvasLayoutEffect(() => {
    // While a structural edit's GRAPH.md write is in flight, the optimistic
    // nodes/edges are the source of truth until the refetch lands. Reconciling
    // against the (still pre-write) composed layout here would flash the edit
    // back to its old state, so skip the reset until the write settles.
    if (pendingGraphEditsRef.current === 0) {
      const nextNodes = stampSelection(composedLayout.nodes)
      setNodes((current) => {
        const equal = nodeListsSemanticallyEqual(current, nextNodes)
        return equal ? current : nextNodes
      })
      setEdges((current) => {
        const equal = edgeListsSemanticallyEqual(current, decoratedComposedEdges)
        return equal ? current : decoratedComposedEdges
      })
    }
    fitInitialViewportOnce(hasLayoutNodes)
    // graphEditsSettledTick: re-run once the last in-flight graph edit settles,
    // reconciling composedLayout changes that arrived while the edit was pending
    // (see beginGraphEdit/endGraphEdit).
  }, [stampSelection, composedLayout.nodes, decoratedComposedEdges, fitInitialViewportOnce, graphEditsSettledTick, hasLayoutNodes, setEdges, setNodes])

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
          node.data.onCancelSequentialOverwrite === handleCancelSequentialOverwrite
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
            onCancelSequentialOverwrite: handleCancelSequentialOverwrite,
          },
        }
      })
      return changed ? nextNodes : currentNodes
    })
  }, [composedLayout.nodes, warningQueue, activeWarningIndex, cancelledNodeIds, handleAllowSequentialOverwrite, handleCancelSequentialOverwrite, setNodes])

  const activeSelectedNodeId = selectionOverride.active ? selectionOverride.nodeId : selectedNodeId
  useEffect(() => {
    setNodes((currentNodes) => {
      let changed = false
      const nextNodes = currentNodes.map((node) => {
        const selected = node.id === activeSelectedNodeId
        if (node.selected === selected) {
          return node
        }
        changed = true
        return { ...node, selected }
      })
      return changed ? nextNodes : currentNodes
    })
  }, [activeSelectedNodeId, setNodes])

  // n2-canvas #14: a drilled subgraph that is read-only (bundled/public), or whose
  // editable child detail has not resolved yet, must NOT accept a structure edit.
  // Block BEFORE any optimistic mutation so the canvas never writes against the
  // wrong identity nor silently mutates a bundle. Returns true when the edit is
  // blocked. At root depth (not drilled) this is a no-op.
  const blockDrilledEditIfUnwritable = useCallback((): boolean => {
    if (!isDrilled) return false
    if (drilledChildTarget) return false
    if (isDrilledChildReadOnly) {
      toast.error('This subgraph is read-only. Fork it into your workspace to edit.')
    } else {
      toast.error('Loading subgraph. Try again in a moment.')
    }
    return true
  }, [isDrilled, drilledChildTarget, isDrilledChildReadOnly])

  const onConnect = useCallback((connection: Connection) => {
    const source = connection.source
    const target = connection.target
    if (!source || !target) {
      toast.error('Connection endpoints are required')
      return
    }
    const scope = canvasScopeForEndpoints(source, target)
    if (!scope) {
      toast.error('Connect nodes within the same graph.')
      return
    }
    const localConnection = localConnectionEndpoints({ source, target })
    if (localConnection.source === localConnection.target) {
      toast.error('A phase cannot depend on itself')
      return
    }
    const visibleNodes = nodesRef.current
    const sourceNode = visibleNodes.find((node): node is SkillGraphNode => node.id === source && node.type === 'skill')
    const targetNode = visibleNodes.find((node): node is SkillGraphNode => node.id === target && node.type === 'skill')
    const isGraphInputConnection = localConnection.source === INPUT_ID && Boolean(targetNode)
    const isGraphOutputConnection = Boolean(sourceNode) && localConnection.target === OUTPUT_ID
    const isPhaseDependencyConnection = Boolean(sourceNode) && Boolean(targetNode)
    if (!isGraphInputConnection && !isGraphOutputConnection && !isPhaseDependencyConnection) {
      toast.error('Connect Input to a phase, phase to phase, or phase to Output')
      return
    }
    const dependencySource = localConnection.source === INPUT_ID ? 'input' : localConnection.source
    if (targetNode && targetNode.data.dependsOn.includes(dependencySource)) {
      toast.error('This dependency already exists')
      return
    }
    if (sourceNode && localConnection.target === OUTPUT_ID && sourceNode.data.isOutput === true) {
      toast.error('This output marker already exists')
      return
    }
    let childArgs: readonly [ChildSaveTarget] | readonly []
    if (scope.parentNodeId) {
      const childTarget = expandedChildSaveTarget(scope.parentNodeId)
      if (!childTarget) {
        toast.error('Loading subgraph. Try again in a moment.')
        return
      }
      childArgs = [childTarget]
    } else {
      if (blockDrilledEditIfUnwritable()) {
        return
      }
      childArgs = drilledChildTarget ? [drilledChildTarget] : []
    }

    setEdges((current) => addEdge(
      decorateContextEdge(createContextEdge(source, target), edgeHandlers),
      current,
    ))
    setNodes((current) => addConnectionToLiveNodes(current, { source, target }, localConnection))
    if (onPersistConnection) {
      beginGraphEdit()
      Promise.resolve(onPersistConnection({ ...connection, ...localConnection }, ...childArgs))
        .catch((persistError: unknown) => {
          toast.error(persistError instanceof Error ? persistError.message : 'Could not persist dependency')
          setEdges(decoratedComposedEdges)
          setNodes(composedLayout.nodes)
        })
        .finally(endGraphEdit)
    }
  }, [beginGraphEdit, blockDrilledEditIfUnwritable, composedLayout.nodes, decoratedComposedEdges, drilledChildTarget, edgeHandlers, endGraphEdit, expandedChildSaveTarget, onPersistConnection, setEdges, setNodes])

  // R4 + n2-canvas #8: drag an existing edge endpoint to a new node = remove the
  // old dependency + add the new one. planEdgeReconnect owns the DECISION (global
  // node / self-dependency / no-op guards). The MUTATION is now a SINGLE atomic
  // serialize/write through onReconnectConnection: the previous code chained
  // onDisconnectConnection().then(onPersistConnection), two serialize round-trips
  // against the same captured skillDetail closure, and the queued persist
  // serialized the pre-disconnect phases with a stale expected_hash, causing backend 409
  // lost-update that left the graph half-mutated. A reconnect that lands back on
  // the same endpoints (no-op) just snaps the edge back without a write. Both
  // real consumers (main canvas + compact SplitEditor canvas) now wire
  // onReconnectConnection; the legacy chained fallback below is kept only as a
  // defensive path for any future surface that mounts GraphCanvas without it.
  const restoreReconnectingEdge = useCallback((edge: Edge<ContextEdgeData>) => {
    reconnectingEdgeRef.current = null
    setEdges((current) => (
      current.some((candidate) => candidate.id === edge.id) ? current : [...current, edge]
    ))
  }, [setEdges])

  const onReconnect = useCallback((oldEdge: Edge<ContextEdgeData>, newConnection: Connection) => {
    if (!newConnection.source || !newConnection.target) {
      toast.error('Edge endpoints must be phase nodes to reconnect.')
      reconnectLandedRef.current = true
      restoreReconnectingEdge(oldEdge)
      return
    }
    const oldScope = canvasScopeForEndpoints(oldEdge.source, oldEdge.target)
    const newScope = canvasScopeForEndpoints(newConnection.source, newConnection.target)
    if (!oldScope || !newScope || oldScope.parentNodeId !== newScope.parentNodeId) {
      toast.error('Reconnect nodes within the same graph.')
      reconnectLandedRef.current = true
      restoreReconnectingEdge(oldEdge)
      return
    }
    const localOldConnection = localConnectionEndpoints({ source: oldEdge.source, target: oldEdge.target })
    const localNewConnection = localConnectionEndpoints({ source: newConnection.source, target: newConnection.target })
    const plan = planEdgeReconnect(
      localOldConnection,
      localNewConnection,
    )
    if (!plan.ok) {
      if (plan.reason !== 'no-op') {
        toast.error(plan.message)
      }
      reconnectLandedRef.current = true
      restoreReconnectingEdge(oldEdge)
      return
    }
    const targetNode = nodesRef.current.find((node): node is SkillGraphNode => (
      node.id === newConnection.target && node.type === 'skill'
    ))
    if (targetNode && targetNode.data.dependsOn.includes(plan.connect.source)) {
      toast.error('This dependency already exists')
      reconnectLandedRef.current = true
      restoreReconnectingEdge(oldEdge)
      return
    }
    let childArgs: readonly [ChildSaveTarget] | readonly []
    if (newScope.parentNodeId) {
      const childTarget = expandedChildSaveTarget(newScope.parentNodeId)
      if (!childTarget) {
        toast.error('Loading subgraph. Try again in a moment.')
        reconnectLandedRef.current = true
        restoreReconnectingEdge(oldEdge)
        return
      }
      childArgs = [childTarget]
    } else {
      if (blockDrilledEditIfUnwritable()) {
        reconnectLandedRef.current = true
        restoreReconnectingEdge(oldEdge)
        return
      }
      childArgs = drilledChildTarget ? [drilledChildTarget] : []
    }

    // Optimistically move the edge to its new endpoints before the write lands.
    // Use the same factory as persisted edges so IO boundary dots never flash
    // while waiting for GRAPH.md to be written and reloaded.
    const optimisticEdge = decorateContextEdge(createContextEdge(newConnection.source, newConnection.target), edgeHandlers)
    reconnectLandedRef.current = true
    reconnectingEdgeRef.current = null
    setEdges((current) => (
      current.some((candidate) => candidate.id === oldEdge.id)
        ? current.map((candidate) => (candidate.id === oldEdge.id ? optimisticEdge : candidate))
        : [...current, optimisticEdge]
    ))
    setNodes((current) => addConnectionToLiveNodes(
      removeConnectionFromLiveNodes(current, oldEdge, plan.disconnect),
      { source: newConnection.source, target: newConnection.target },
      plan.connect,
    ))
    const rollback = (reconnectError: unknown) => {
      toast.error(reconnectError instanceof Error ? reconnectError.message : 'Could not reconnect dependency')
      setEdges(decoratedComposedEdges)
      setNodes(composedLayout.nodes)
    }
    if (onReconnectConnection) {
      beginGraphEdit()
      Promise.resolve(onReconnectConnection(plan.disconnect, plan.connect, ...childArgs)).catch(rollback).finally(endGraphEdit)
      return
    }
    if (!onDisconnectConnection || !onPersistConnection) {
      return
    }
    beginGraphEdit()
    Promise.resolve(onDisconnectConnection(plan.disconnect, ...childArgs))
      .then(() => onPersistConnection({
        ...newConnection,
        source: plan.connect.source,
        target: plan.connect.target,
      }, ...childArgs))
      .catch(rollback)
      .finally(endGraphEdit)
  }, [beginGraphEdit, blockDrilledEditIfUnwritable, composedLayout.nodes, decoratedComposedEdges, drilledChildTarget, edgeHandlers, endGraphEdit, expandedChildSaveTarget, onDisconnectConnection, onPersistConnection, onReconnectConnection, restoreReconnectingEdge, setEdges, setNodes])

  const onReconnectStart = useCallback((
    _event: globalThis.MouseEvent | MouseEvent,
    edge: Edge<ContextEdgeData>,
  ) => {
    reconnectLandedRef.current = false
    reconnectingEdgeRef.current = edge
    setEdges((current) => current.filter((candidate) => candidate.id !== edge.id))
  }, [setEdges])

  // n2-canvas #14: the right-click "Disconnect" menu path. Routes through the same
  // drilled-child target + read-only block as the drag-disconnect path so a menu
  // disconnect inside a drilled child writes the CHILD's GRAPH.md, and a read-only
  // child is blocked. At root depth this is the plain parent disconnect, unchanged.
  const handleMenuDisconnect = useCallback((connection: { source: string; target: string }) => {
    if (!onDisconnectConnection) return
    const scope = canvasScopeForEndpoints(connection.source, connection.target)
    if (!scope) {
      toast.error('Disconnect nodes within the same graph.')
      return
    }
    let childArgs: readonly [ChildSaveTarget] | readonly []
    if (scope.parentNodeId) {
      const childTarget = expandedChildSaveTarget(scope.parentNodeId)
      if (!childTarget) {
        toast.error('Loading subgraph. Try again in a moment.')
        return
      }
      childArgs = [childTarget]
    } else {
      if (blockDrilledEditIfUnwritable()) return
      childArgs = drilledChildTarget ? [drilledChildTarget] : []
    }
    const localConnection = localConnectionEndpoints(connection)
    setEdges((current) => current.filter((candidate) => (
      candidate.source !== connection.source || candidate.target !== connection.target
    )))
    setNodes((current) => removeConnectionFromLiveNodes(current, connection, localConnection))
    beginGraphEdit()
    void Promise.resolve(onDisconnectConnection(localConnection, ...childArgs))
      .catch((disconnectError: unknown) => {
        toast.error(disconnectError instanceof Error ? disconnectError.message : 'Could not disconnect dependency')
        setEdges(decoratedComposedEdges)
        setNodes(composedLayout.nodes)
      })
      .finally(endGraphEdit)
  }, [beginGraphEdit, blockDrilledEditIfUnwritable, composedLayout.nodes, decoratedComposedEdges, drilledChildTarget, endGraphEdit, expandedChildSaveTarget, onDisconnectConnection, setEdges, setNodes])

  const handleMenuDeletePhase = useCallback((nodeId: string) => {
    if (!onDeletePhase) return
    const parentNodeId = previewNodeParentId(nodeId)
    const phaseId = phaseIdFromCanvasNodeId(nodeId)
    let childArgs: readonly [ChildSaveTarget] | readonly []
    if (parentNodeId) {
      const childTarget = expandedChildSaveTarget(parentNodeId)
      if (!childTarget) {
        toast.error('Loading subgraph. Try again in a moment.')
        return
      }
      childArgs = [childTarget]
    } else {
      if (blockDrilledEditIfUnwritable()) return
      childArgs = drilledChildTarget ? [drilledChildTarget] : []
    }
    void Promise.resolve(onDeletePhase(phaseId, ...childArgs))
      .catch((deleteError: unknown) => {
        toast.error(deleteError instanceof Error ? deleteError.message : 'Could not delete node')
      })
  }, [blockDrilledEditIfUnwritable, drilledChildTarget, expandedChildSaveTarget, onDeletePhase])

  const handleOpenCreatePhaseDialog = useCallback((kind: NewPhaseKind) => {
    if (blockDrilledEditIfUnwritable()) return
    setCreatePhaseKind(kind)
  }, [blockDrilledEditIfUnwritable])

  const createPhaseInitialName = useMemo(
    () => createPhaseKind ? defaultPhaseId(skillDetail, createPhaseKind) : '',
    [createPhaseKind, skillDetail],
  )

  // R4: an edge endpoint dragged off every handle and released (isValid not
  // true, and no onReconnect fired) = the user pulled the wire loose, so drop
  // the dependency via the same disconnect and serialize path.
  const onReconnectEnd = useCallback((
    _event: globalThis.MouseEvent | globalThis.TouchEvent,
    edge: Edge<ContextEdgeData>,
    _handleType: 'source' | 'target',
    connectionState: FinalConnectionState,
  ) => {
    if (reconnectLandedRef.current) {
      return
    }
    if (connectionState.isValid === true) {
      restoreReconnectingEdge(edge)
      return
    }
    const localConnection = localConnectionEndpoints({ source: edge.source, target: edge.target })
    if (!onDisconnectConnection) {
      restoreReconnectingEdge(edge)
      return
    }
    const scope = canvasScopeForEndpoints(edge.source, edge.target)
    if (!scope) {
      toast.error('Disconnect nodes within the same graph.')
      restoreReconnectingEdge(edge)
      return
    }
    let childArgs: readonly [ChildSaveTarget] | readonly []
    if (scope.parentNodeId) {
      const childTarget = expandedChildSaveTarget(scope.parentNodeId)
      if (!childTarget) {
        toast.error('Loading subgraph. Try again in a moment.')
        restoreReconnectingEdge(edge)
        return
      }
      childArgs = [childTarget]
    } else {
      if (blockDrilledEditIfUnwritable()) {
        restoreReconnectingEdge(edge)
        return
      }
      childArgs = drilledChildTarget ? [drilledChildTarget] : []
    }
    reconnectingEdgeRef.current = null
    setEdges((current) => current.filter((candidate) => candidate.id !== edge.id))
    setNodes((current) => removeConnectionFromLiveNodes(current, edge, localConnection))
    beginGraphEdit()
    Promise.resolve(onDisconnectConnection(localConnection, ...childArgs))
      .catch((disconnectError: unknown) => {
        toast.error(disconnectError instanceof Error ? disconnectError.message : 'Could not disconnect dependency')
        setEdges(decoratedComposedEdges)
        setNodes(composedLayout.nodes)
      })
      .finally(endGraphEdit)
  }, [beginGraphEdit, blockDrilledEditIfUnwritable, composedLayout.nodes, decoratedComposedEdges, drilledChildTarget, endGraphEdit, expandedChildSaveTarget, onDisconnectConnection, restoreReconnectingEdge, setEdges, setNodes])

  const handlePaneClick = useCallback(() => {
    cancelPendingNodeClickAction()
    syncCanvasSelection(null)
    onNodeDeselect?.()
    setEdgeMenuConnection(null)
    setNodeMenuPhaseId(null)
    // Clicking empty canvas clears the workspace: close the open side panel AND
    // the file editor(s). It no longer opens the graph.md panel.
    onPanelChange?.(null)
    onCloseEditors?.()
  }, [cancelPendingNodeClickAction, onCloseEditors, onNodeDeselect, onPanelChange, syncCanvasSelection])

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        <section ref={canvasRef} className="studio-canvas-pane-bg relative h-full min-h-0">
      {/* SWR keeps the last good skillDetail when a background revalidation
          fails (sidecar restart / transient network), so `error` + stale data
          is a normal state. The full-canvas bg-background/80 veil is ONLY for
          "nothing to show" — over a rendered graph it washed the entire canvas
          white and blocked pointer events (2026-07-02 亮色"光晕"根因). With
          data on screen the failure downgrades to a corner chip, mirroring the
          Loading chip below. */}
      {error && !skillDetail ? (
        <div className="absolute inset-0 z-10 grid place-items-center bg-background/80 p-8">
          <div className="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            Failed to load skill graph.
          </div>
        </div>
      ) : null}

      {/* Both corner chips shift left of the right drawer overlay (z-30 covers
          a plain right-4 chip when Copilot is open) — same safe-area offset
          the minimap already uses. */}
      {error && skillDetail ? (
        <div
          className="absolute top-4 z-10 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive shadow-sm"
          style={{ right: 'calc(var(--studio-canvas-right-safe-area, 0px) + 1rem)' }}
        >
          Graph refresh failed — showing the last loaded graph.
        </div>
      ) : null}

      {isLoading ? (
        <div
          className="absolute top-4 z-10 rounded-md border border-border bg-card px-3 py-2 text-xs text-muted-foreground shadow-sm"
          style={{ right: 'calc(var(--studio-canvas-right-safe-area, 0px) + 1rem)' }}
        >
          Loading graph...
        </div>
      ) : null}

      {/* compact remains available for explicit read-only projections. The file
          editor split uses normal canvas mode so authoring behaviour stays the
          same when the canvas is squeezed into the lower pane. */}
      <ReactFlow
        className={[isViewportReady ? '' : HIDDEN_INITIAL_VIEWPORT_CLASS, canvasLocked ? 'canvas-locked' : ''].filter(Boolean).join(' ') || undefined}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={handleNodesChange}
        onEdgesChange={onEdgesChange}
        nodesConnectable={canEditCanvas && !canvasLocked}
        nodesDraggable={!compact && !canvasLocked}
        deleteKeyCode={compact ? null : undefined}
        onConnect={compact ? undefined : onConnect}
        edgesReconnectable={canEditCanvas && !canvasLocked}
        panOnDrag={!canvasLocked}
        zoomOnDoubleClick={!canvasLocked}
        zoomOnPinch={!canvasLocked}
        zoomOnScroll={!canvasLocked}
        onReconnectStart={compact ? undefined : onReconnectStart}
        onReconnect={compact ? undefined : onReconnect}
        onReconnectEnd={compact ? undefined : onReconnectEnd}
        onPaneContextMenu={(event) => {
          if (isEdgeContextTarget(event.target)) {
            return
          }
          // Remember where the menu opened (flow coords) so "Add node" can place
          // the new node right here instead of the auto-layout default.
          const instance = reactFlowInstanceRef.current
          lastPaneContextFlowPositionRef.current = instance
            ? instance.screenToFlowPosition({ x: event.clientX, y: event.clientY })
            : null
          setEdgeMenuConnection(null)
          setNodeMenuPhaseId(null)
        }}
        onPaneClick={handlePaneClick}
        onNodeContextMenu={(_, node) => {
          setEdgeMenuConnection(null)
          setNodeMenuPhaseId(
            node.type === 'skill'
              ? node.id
              : null,
          )
        }}
        onEdgeContextMenu={compact ? undefined : (event, edge) => {
          setNodeMenuPhaseId(null)
          if (edge.type !== 'contextEdge') {
            setEdgeMenuConnection(null)
            return
          }
          openEdgeContextMenu(event, { source: edge.source, target: edge.target })
        }}
        onNodeClick={(_, node) => {
          if (node.type === 'subgraphGroup') return
          cancelPendingNodeClickAction()
          const wasSelected = isCanvasNodeSelected(node.id)
          syncCanvasSelection(node.id)
          if (node.type === 'globalInput' || node.type === 'globalOutput') {
            // Carry the boundary identity so the i/o panel scopes to input- or
            // output-only (handleBoundarySelect clears any phase selection).
            onBoundarySelect?.(node.type === 'globalInput' ? 'input' : 'output')
            onPanelChange?.('input')
            return
          }
          if (node.type === 'skill') {
            onNodeSelect?.({ id: skillNodePhaseId(node), data: node.data })
            // First click selects/highlights only. The SECOND click on an
            // already-selected node opens the last-recorded panel (deferred so a
            // double-click opens the editor instead of flashing the panel open).
            if (wasSelected) {
              pendingNodeClickActionRef.current = setTimeout(() => {
                pendingNodeClickActionRef.current = null
                if (onOpenSelectedNodePanel) {
                  onOpenSelectedNodePanel()
                } else {
                  onPanelChange?.('properties')
                }
              }, 220)
            }
          }
        }}
        onNodeDragStart={(_, node) => {
          if (node.type === 'subgraphGroup') return
          syncCanvasSelection(node.id)
          if (node.type === 'skill') {
            onNodeSelect?.({ id: skillNodePhaseId(node), data: node.data })
          }
        }}
        selectNodesOnDrag
        onNodeDoubleClick={(_, node) => {
          if (node.type === 'subgraphGroup') return
          cancelPendingNodeClickAction()
          syncCanvasSelection(node.id)
          if (node.type === 'globalInput' || node.type === 'globalOutput') {
            onBoundarySelect?.(node.type === 'globalInput' ? 'input' : 'output')
            onPanelChange?.('input')
            return
          }
          if (node.type === 'skill') {
            const phaseId = skillNodePhaseId(node)
            // Double-click opens the node's source file in the editor — for BOTH
            // subgraph nodes (their SUBGRAPH.md) and leaf phases. Drilling INTO a
            // child graph now lives on the expanded subgraph board's "open canvas"
            // button (see SubgraphGroupNode), not on this double-click.
            onNodeSelect?.({ id: phaseId, data: node.data })
            openNodeFile(node)
          }
        }}
        onInit={(instance) => {
          reactFlowInstanceRef.current = instance
          fitViewRef.current = runFitView
          fitInitialViewportOnce(hasLayoutNodes)
        }}
        nodeOrigin={CENTER_NODE_ORIGIN}
        minZoom={0.35}
        maxZoom={1.4}
        proOptions={{ hideAttribution: true }}
      >
        <SubgraphBridgeInternalsUpdater nodes={nodes} />
        <Background gap={18} size={1} color="var(--studio-canvas-dot)" />
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
        {!compact ? <SkillMiniMap visible={!hideMiniMap} /> : null}
        {drillStack.length > 0 || isChildGraphLoading || childGraphError ? (
          <Panel position="top-left" className="studio-canvas-top-left-panel">
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
                  <span>Loading subgraph...</span>
                </div>
              ) : null}
              {childGraphError ? (
                <div className="rounded-md border border-destructive/40 bg-destructive/10 px-2.5 py-1.5 text-xs text-destructive shadow-sm">
                  {childGraphError}
                </div>
              ) : null}
            </div>
          </Panel>
        ) : null}
      </ReactFlow>
        </section>
      </ContextMenuTrigger>
      <CanvasContextMenuContent
        edgeMenuConnection={edgeMenuConnection}
        nodeMenuPhaseId={nodeMenuPhaseId}
        canvasLocked={canvasLocked}
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
        onFitView={handleFitView}
        onToggleCanvasLock={handleToggleCanvasLock}
        onCreatePhase={canEditCanvas ? handleOpenCreatePhaseDialog : undefined}
        onDeletePhase={handleMenuDeletePhase}
        onDisconnectConnection={handleMenuDisconnect}
        onCloseEdgeMenu={() => {
          setEdgeMenuConnection(null)
          setNodeMenuPhaseId(null)
        }}
        readOnly={compact}
      />
      <PhaseNameDialog
        open={createPhaseKind !== null}
        kind={createPhaseKind}
        initialName={createPhaseInitialName}
        skillDetail={skillDetail}
        onOpenChange={(open) => {
          if (!open) {
            setCreatePhaseKind(null)
          }
        }}
        onSubmit={(phaseId) => {
          const kind = createPhaseKind
          if (!kind || !onCreatePhase) return
          setCreatePhaseKind(null)
          // Same drilled-child routing as delete/connect: a read-only drilled child
          // is blocked with a toast; an editable one routes the create to its target
          // so the new node writes the CHILD's GRAPH.md.
          if (blockDrilledEditIfUnwritable()) return
          // Drop the new node where the user right-clicked (if captured).
          const placement = lastPaneContextFlowPositionRef.current
          if (placement) {
            pendingCreatePositionsRef.current.set(phaseId, placement)
            lastPaneContextFlowPositionRef.current = null
          }
          void Promise.resolve(onCreatePhase(kind, phaseId, drilledChildTarget ?? undefined))
            .catch((createError: unknown) => {
              toast.error(createError instanceof Error ? createError.message : 'Could not create phase')
            })
        }}
      />
    </ContextMenu>
  )
}

const ADD_PHASE_OPTIONS: ReadonlyArray<{ kind: NewPhaseKind; label: string }> = [
  { kind: 'skill', label: 'Agent Phase' },
  { kind: 'logic', label: 'Logic Phase' },
  { kind: 'subgraph', label: 'Subgraph Phase' },
]

// Display label for the canvas shortcut modifier: ⌘ on macOS, Ctrl+ elsewhere.
const SHORTCUT_MOD = typeof navigator !== 'undefined' && /mac/i.test(navigator.platform) ? '⌘' : 'Ctrl+'

export function CanvasContextMenuContent({
  edgeMenuConnection,
  nodeMenuPhaseId,
  canvasLocked,
  onZoomIn,
  onZoomOut,
  onFitView,
  onToggleCanvasLock,
  onCreatePhase,
  onDeletePhase,
  onDisconnectConnection,
  onCloseEdgeMenu,
  readOnly,
}: {
  edgeMenuConnection: { source: string; target: string } | null
  nodeMenuPhaseId?: string | null
  canvasLocked?: boolean
  onZoomIn?: () => void
  onZoomOut?: () => void
  onFitView?: () => void
  onToggleCanvasLock?: () => void
  onCreatePhase?: (kind: NewPhaseKind) => Promise<void> | void
  onDeletePhase?: (phaseId: string) => Promise<void> | void
  onDisconnectConnection?: (connection: { source: string; target: string }) => Promise<void> | void
  onCloseEdgeMenu?: () => void
  readOnly?: boolean
}) {
  // Explicit read-only projection: no edit affordances at all, so right-click
  // offers neither Disconnect nor Add Phase Node.
  if (readOnly) {
    return null
  }
  return (
    // No scroll: show the whole menu (override the default available-height clamp).
    // Wider min-width so the label and the right-aligned shortcut aren't cramped.
    <ContextMenuContent className="min-w-52 max-h-none overflow-visible">
      {/* Zoom / Fit are no-ops while the canvas is locked. Shortcuts mirror the
          window-level keydown handler in GraphCanvas (#3.2). */}
      <ContextMenuItem onSelect={onZoomIn} disabled={canvasLocked}>
        Zoom in
        <ContextMenuShortcut>{SHORTCUT_MOD}=</ContextMenuShortcut>
      </ContextMenuItem>
      <ContextMenuItem onSelect={onZoomOut} disabled={canvasLocked}>
        Zoom out
        <ContextMenuShortcut>{SHORTCUT_MOD}−</ContextMenuShortcut>
      </ContextMenuItem>
      <ContextMenuItem onSelect={onFitView} disabled={canvasLocked}>
        Fit view
        <ContextMenuShortcut>{SHORTCUT_MOD}0</ContextMenuShortcut>
      </ContextMenuItem>
      <ContextMenuItem onSelect={onToggleCanvasLock}>
        {canvasLocked ? 'Unlock canvas' : 'Lock canvas'}
        <ContextMenuShortcut>{SHORTCUT_MOD}L</ContextMenuShortcut>
      </ContextMenuItem>
      <ContextMenuSeparator />
      {edgeMenuConnection ? (
        <ContextMenuItem
          onSelect={() => {
            void onDisconnectConnection?.(edgeMenuConnection)
            onCloseEdgeMenu?.()
          }}
        >
          Disconnect
        </ContextMenuItem>
      ) : nodeMenuPhaseId && onDeletePhase ? (
        <ContextMenuItem variant="destructive" onSelect={() => { void onDeletePhase(nodeMenuPhaseId) }}>
          <Trash2 className="size-3.5" />
          Delete node
          <ContextMenuShortcut>Del</ContextMenuShortcut>
        </ContextMenuItem>
      ) : onCreatePhase ? (
        // Add-node options flattened directly into the menu (no nested submenu).
        <>
          <ContextMenuLabel>Add node</ContextMenuLabel>
          {ADD_PHASE_OPTIONS.map((option) => (
            <ContextMenuItem key={option.kind} onSelect={() => { void onCreatePhase?.(option.kind) }}>
              {option.label}
            </ContextMenuItem>
          ))}
        </>
      ) : null}
    </ContextMenuContent>
  )
}
