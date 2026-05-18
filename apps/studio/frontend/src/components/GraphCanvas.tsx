import '@xyflow/react/dist/style.css'

import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, Bot, Briefcase, CheckCircle2, Circle, Code, Minus, Network, Pause, Plus, Radio, Workflow } from 'lucide-react'
import yaml from 'js-yaml'
import { toast } from 'sonner'
import type { IoDeclaration, PhaseDef, SkillDetail, SkillManifest } from '../api/types'
import { CycleDetectedError, getAutoLayoutedElements } from '../lib/layout'
import { ContextEdge, type ContextEdgeData } from './edges/ContextEdge'
import { GlobalInputNode, GlobalOutputNode } from './nodes/GlobalInputOutputNode'
import { SubgraphInline } from './studio/SubgraphInline'
import { useOptionalWorkspaceContext } from './studio/WorkspaceContext'
import type { PanelKind } from './studio/Toolbar'
import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip'

export type SkillNodeStatus = 'idle' | 'running' | 'success' | 'error' | 'paused' | 'breakpoint'

export interface SkillGraphNodeData extends Record<string, unknown> {
  label: string
  mode: string
  role?: string | null
  tools?: string[]
  filePath?: string
  status: SkillNodeStatus
  dependsOn: string[]
  subgraphPath?: string | null
  subagents?: SubagentRef[]
  isExpanded?: boolean
  onToggleSubgraph?: () => void
}

export type SkillGraphNode = Node<SkillGraphNodeData, 'skill'>

export interface SubagentRef {
  name: string
  path: string
  description: string
}

type PhaseKind = 'LOGIC' | 'AGENT' | 'SUBGRAPH'

export interface GlobalNodeData extends Record<string, unknown> {
  type: 'global-input' | 'global-output'
  schema: IoDeclaration
}

export type GraphCanvasNode =
  | Node<SkillGraphNodeData, 'skill'>
  | Node<GlobalNodeData, 'globalInput'>
  | Node<GlobalNodeData, 'globalOutput'>

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

const INPUT_ID = '__global_input__'
const OUTPUT_ID = '__global_output__'
const EMPTY_IO: IoDeclaration = { inputs: [], outputs: [] }

const STATUS_STYLE: Record<SkillNodeStatus, { label: string, className: string, icon: typeof Circle }> = {
  idle: {
    label: 'Idle',
    className: 'border-border bg-card text-muted-foreground',
    icon: Circle,
  },
  running: {
    label: 'Running',
    className: 'animate-pulse-primary border-primary bg-primary/10 text-primary',
    icon: Radio,
  },
  success: {
    label: 'Success',
    className: 'border-emerald-500/45 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
    icon: CheckCircle2,
  },
  error: {
    label: 'Error',
    className: 'border-destructive/50 bg-destructive/10 text-destructive',
    icon: AlertTriangle,
  },
  paused: {
    label: 'Paused',
    className: 'border-amber-500/45 bg-amber-500/10 text-amber-700 dark:text-amber-300',
    icon: Pause,
  },
  breakpoint: {
    label: 'Breakpoint',
    className: 'border-fuchsia-500/45 bg-fuchsia-500/10 text-fuchsia-700 dark:text-fuchsia-300',
    icon: Workflow,
  },
}

function phaseKindLabel(data: Pick<SkillGraphNodeData, 'mode' | 'subgraphPath'>): PhaseKind {
  if (data.subgraphPath || data.mode === 'subgraph') return 'SUBGRAPH'
  if (data.mode === 'skill' || data.mode === 'llm') return 'AGENT'
  return 'LOGIC'
}

function phaseKindFile(data: Pick<SkillGraphNodeData, 'mode' | 'subgraphPath'>): 'LOGIC.md' | 'SKILL.md' | 'SUBGRAPH.md' {
  const kind = phaseKindLabel(data)
  if (kind === 'SUBGRAPH') return 'SUBGRAPH.md'
  if (kind === 'AGENT') return 'SKILL.md'
  return 'LOGIC.md'
}

function phaseKindIcon(kind: PhaseKind): typeof Bot {
  if (kind === 'LOGIC') return Code
  if (kind === 'SUBGRAPH') return Network
  return Bot
}

export function SkillNode({ data, selected }: NodeProps<SkillGraphNode>) {
  const style = STATUS_STYLE[data.status]
  const StatusIcon = style.icon
  const kind = phaseKindLabel(data)
  const KindIcon = phaseKindIcon(kind)
  const subagentCount = data.subagents?.length ?? 0

  return (
    <div
      className={[
        'relative min-w-[240px] cursor-pointer rounded-md border bg-card p-3 text-card-foreground shadow-sm transition-colors',
        data.subgraphPath ? 'pb-5' : '',
        selected ? 'border-primary ring-2 ring-primary/30' : 'border-border',
      ].join(' ')}
      onDoubleClick={(event) => {
        if (data.subgraphPath) {
          event.stopPropagation()
        }
      }}
    >
      <Handle type="target" position={Position.Left} className="!size-2.5 !border-background !bg-primary" />
      <div className="flex items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
          <KindIcon className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-foreground">{data.label}</div>
          <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
            <span>{kind}</span>
            {subagentCount > 0 ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    aria-label={`${subagentCount} subagents available`}
                    className="inline-flex size-5 items-center justify-center rounded-md border border-border bg-muted text-muted-foreground"
                  >
                    <Briefcase className="size-3" />
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">{subagentCount} subagents available</TooltipContent>
              </Tooltip>
            ) : null}
          </div>
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className={['inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium', style.className].join(' ')}>
              <StatusIcon className="size-3" />
              {style.label}
            </span>
          </TooltipTrigger>
          <TooltipContent side="top">{style.label}</TooltipContent>
        </Tooltip>
      </div>
      {data.subgraphPath ? (
        <button
          type="button"
          aria-label={data.isExpanded ? '收起子图' : '展开子图'}
          onClick={(event) => {
            event.stopPropagation()
            data.onToggleSubgraph?.()
          }}
          className="absolute bottom-0 left-1/2 inline-flex size-5 -translate-x-1/2 translate-y-1/2 items-center justify-center rounded-full border border-border bg-card text-foreground shadow-sm transition-colors hover:border-primary"
        >
          {data.isExpanded ? <Minus className="size-3" /> : <Plus className="size-3" />}
        </button>
      ) : null}
      {data.subgraphPath && data.isExpanded ? (
        <SubgraphInline path={data.subgraphPath} parentLabel={data.label} />
      ) : null}
      <Handle type="source" position={Position.Right} className="!size-2.5 !border-background !bg-primary" />
    </div>
  )
}

const nodeTypes = {
  skill: SkillNode,
  globalInput: GlobalInputNode,
  globalOutput: GlobalOutputNode,
}

const edgeTypes = {
  contextEdge: ContextEdge,
}

function normalizeDependsOn(value: string | string[] | undefined): string[] {
  if (Array.isArray(value)) {
    return value.filter(Boolean)
  }
  return value ? [value] : []
}

function phasesFromManifest(manifest: SkillManifest | undefined, skillId: string): PhaseDef[] {
  if (manifest?.schema_version === '2.1') {
    return manifest.phases.map((phase) => ({
      name: phase.id,
      mode: 'logic',
      model_override: null,
      depends_on: phase.depends_on,
      execute_steps: [],
      validator: null,
    }))
  }

  if (manifest?.type === 'graph') {
    return manifest.phases
  }

  if (manifest?.type === 'agent') {
    return [{
      name: manifest.name,
      mode: 'llm',
      model_override: manifest.model_override,
      prompt: null,
      user_prompt_template: manifest.user_prompt_template,
      agent_tools: manifest.agent_tools,
      steps: manifest.agent_profile.steps,
      domain_protocols: manifest.agent_profile.domain_protocols,
      references: manifest.agent_profile.references,
      few_shot_examples: manifest.agent_profile.few_shot_examples,
      context_access: manifest.agent_profile.context_access,
      llm_role: manifest.agent_profile.llm_role,
      adopted_persona: manifest.adopted_persona,
      max_iterations: null,
      max_retries: null,
      max_nudges: null,
      dead_end_threshold: null,
      validator: null,
      validator_optional: false,
      retry_target: null,
      hoist_to: null,
      output_schema: null,
      output_example: null,
      output_schema_md: null,
      output_example_md: null,
    }]
  }

  return [
    {
      name: `${skillId}-draft`,
      mode: 'llm',
      model_override: null,
      prompt: null,
      user_prompt_template: null,
      agent_tools: [],
      steps: ['Draft prompt'],
      domain_protocols: [],
      references: [],
      few_shot_examples: [],
      context_access: ['working_memory'],
      llm_role: 'Agent',
      adopted_persona: null,
      max_iterations: null,
      max_retries: null,
      max_nudges: null,
      dead_end_threshold: null,
      validator: null,
      validator_optional: false,
      retry_target: null,
      hoist_to: null,
      output_schema: null,
      output_example: null,
      output_schema_md: null,
      output_example_md: null,
    },
    {
      name: `${skillId}-review`,
      mode: 'logic',
      model_override: null,
      depends_on: `${skillId}-draft`,
      execute_steps: ['Validate output'],
      validator: null,
    },
  ]
}

function ioFromManifest(manifest: SkillManifest | undefined): IoDeclaration {
  if (manifest?.schema_version === '2.1') {
    return EMPTY_IO
  }
  return manifest?.type === 'graph' ? manifest.io : EMPTY_IO
}

function subgraphRefFromFile(content: string | undefined): string | null {
  if (!content) return null
  const block = content.match(/<sub_skill_ref>\s*([\s\S]*?)\s*<\/sub_skill_ref>/)
  if (block?.[1]) return block[1].trim()
  const yaml = content.match(/^sub_skill_ref:\s*['"]?([^'"\n]+)['"]?/m)
  return yaml?.[1]?.trim() ?? null
}

function subagentsFromUnknown(value: unknown): SubagentRef[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return []
    const record = item as Record<string, unknown>
    if (typeof record.name !== 'string' || typeof record.path !== 'string' || typeof record.description !== 'string') {
      return []
    }
    return [{ name: record.name, path: record.path, description: record.description }]
  })
}

function phaseFrontmatter(content: string | undefined): Record<string, unknown> | null {
  if (!content) return null
  const match = /^---\n([\s\S]*?)\n---/m.exec(content)
  if (!match) return null
  const parsed = yaml.load(match[1])
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
  return parsed as Record<string, unknown>
}

function subagentsForPhase(detail: SkillDetail | undefined, phaseId: string): SubagentRef[] {
  const topologyItem = detail?.graph_topology?.find((phase) => phase.id === phaseId) as ({ subagents?: unknown } | undefined)
  const topologySubagents = subagentsFromUnknown(topologyItem?.subagents)
  if (topologySubagents.length > 0) return topologySubagents

  const frontmatter = phaseFrontmatter(detail?.files?.[`phases/${phaseId}/SKILL.md`])
  const phaseConfig = frontmatter?.phase_config
  if (!phaseConfig || typeof phaseConfig !== 'object' || Array.isArray(phaseConfig)) return []
  return subagentsFromUnknown((phaseConfig as Record<string, unknown>).subagents)
}

function buildNodes(
  skillId: string,
  detail: SkillDetail | undefined,
  expandedSubgraphs: Set<string>,
  onToggleSubgraph: (nodeId: string) => void,
  statusByNodeId: Record<string, SkillNodeStatus>,
): GraphCanvasNode[] {
  const phases = phasesFromManifest(detail?.manifest, skillId)
  const io = ioFromManifest(detail?.manifest)
  const topologyById = new Map((detail?.graph_topology ?? []).map((phase) => [phase.id, phase]))
  const phaseNodes: SkillGraphNode[] = phases.map((phase, index) => ({
    id: phase.name,
    type: 'skill',
    position: { x: 160 + (index % 2) * 320, y: 80 + index * 150 },
      data: {
        label: phase.name,
        mode: topologyById.get(phase.name)?.mode ?? phase.mode,
        role: phase.mode === 'llm' ? phase.llm_role : null,
        tools: phase.mode === 'llm' ? phase.agent_tools : [],
        subagents: subagentsForPhase(detail, phase.name),
        filePath: `phases/${phase.name}/${phaseKindFile({
          mode: topologyById.get(phase.name)?.mode ?? phase.mode,
          subgraphPath: phase.subgraph ?? subgraphRefFromFile(detail?.files?.[`phases/${phase.name}/SUBGRAPH.md`]),
        })}`,
        status: statusByNodeId[phase.name] ?? (index === 0 ? 'success' : 'idle'),
      dependsOn: topologyById.get(phase.name)?.depends_on ?? normalizeDependsOn(phase.depends_on),
      subgraphPath: phase.subgraph ?? subgraphRefFromFile(detail?.files?.[`phases/${phase.name}/SUBGRAPH.md`]),
      isExpanded: expandedSubgraphs.has(phase.name),
      onToggleSubgraph: (phase.subgraph ?? detail?.files?.[`phases/${phase.name}/SUBGRAPH.md`])
        ? () => onToggleSubgraph(phase.name)
        : undefined,
    },
  }))
  return [
    {
      id: INPUT_ID,
      type: 'globalInput',
      position: { x: 0, y: 0 },
      data: { type: 'global-input', schema: io } satisfies GlobalNodeData,
    },
    ...phaseNodes,
    {
      id: OUTPUT_ID,
      type: 'globalOutput',
      position: { x: 0, y: 0 },
      data: { type: 'global-output', schema: io } satisfies GlobalNodeData,
    },
  ]
}

function contextEdge(source: string, target: string): Edge<ContextEdgeData> {
  return {
    id: `${source}->${target}`,
    source,
    target,
    type: 'contextEdge',
    data: {
      hasTraceData: false,
      sourcePhaseId: source,
      targetPhaseId: target,
    },
    style: { strokeWidth: 1.5 },
  }
}

export function buildEdges(phaseNodes: SkillGraphNode[]): Edge<ContextEdgeData>[] {
  if (phaseNodes.length === 0) {
    return [contextEdge(INPUT_ID, OUTPUT_ID)]
  }

  const dependents = new Map<string, Set<string>>()
  for (const node of phaseNodes) {
    for (const dependency of node.data.dependsOn) {
      const targets = dependents.get(dependency) ?? new Set<string>()
      targets.add(node.id)
      dependents.set(dependency, targets)
    }
  }

  const edges: Edge<ContextEdgeData>[] = []
  for (const node of phaseNodes) {
    for (const source of node.data.dependsOn) {
      edges.push(contextEdge(source, node.id))
    }
    if (node.data.dependsOn.length === 0) {
      edges.push(contextEdge(INPUT_ID, node.id))
    }
    if (!dependents.has(node.id) || dependents.get(node.id)?.size === 0) {
      edges.push(contextEdge(node.id, OUTPUT_ID))
    }
  }
  return edges
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
