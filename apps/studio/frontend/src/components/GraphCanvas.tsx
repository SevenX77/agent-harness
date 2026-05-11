import '@xyflow/react/dist/style.css'

import {
  Background,
  Controls,
  Handle,
  MarkerType,
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
import { useCallback, useEffect, useMemo } from 'react'
import { AlertTriangle, Bot, CheckCircle2, Circle, Pause, Radio, Workflow } from 'lucide-react'
import type { PhaseDef, SkillDetail, SkillManifest } from '../api/types'

export type SkillNodeStatus = 'idle' | 'running' | 'success' | 'error' | 'paused' | 'breakpoint'

export interface SkillGraphNodeData extends Record<string, unknown> {
  label: string
  mode: string
  role?: string | null
  status: SkillNodeStatus
  dependsOn: string[]
  subgraphPath?: string | null
}

export type SkillGraphNode = Node<SkillGraphNodeData>

interface GraphCanvasProps {
  skillId: string
  skillDetail?: SkillDetail
  isLoading?: boolean
  error?: unknown
  selectedNodeId?: string | null
  onNodeSelect?: (nodeId: string) => void
}

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

function SkillNode({ data, selected }: NodeProps<SkillGraphNode>) {
  const style = STATUS_STYLE[data.status]
  const StatusIcon = style.icon

  return (
    <div
      className={[
        'min-w-[240px] rounded-md border bg-card p-3 text-card-foreground shadow-sm transition-colors',
        selected ? 'border-primary ring-2 ring-primary/30' : 'border-border',
      ].join(' ')}
    >
      <Handle type="target" position={Position.Top} className="!size-2.5 !border-background !bg-primary" />
      <div className="flex items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
          <Bot className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-foreground">{data.label}</div>
          <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
            <span className="uppercase">{data.mode}</span>
            {data.role ? <span className="truncate">{data.role}</span> : null}
          </div>
        </div>
        <span className={['inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium', style.className].join(' ')}>
          <StatusIcon className="size-3" />
          {style.label}
        </span>
      </div>
      {data.dependsOn.length > 0 ? (
        <div className="mt-3 rounded-md border border-border bg-muted/40 px-2 py-1 text-xs text-muted-foreground">
          depends_on: {data.dependsOn.join(', ')}
        </div>
      ) : null}
      <Handle type="source" position={Position.Bottom} className="!size-2.5 !border-background !bg-primary" />
    </div>
  )
}

const nodeTypes = {
  skill: SkillNode,
}

function normalizeDependsOn(value: string | string[] | undefined): string[] {
  if (Array.isArray(value)) {
    return value.filter(Boolean)
  }
  return value ? [value] : []
}

function phasesFromManifest(manifest: SkillManifest | undefined, skillId: string): PhaseDef[] {
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

function buildNodes(skillId: string, detail?: SkillDetail): SkillGraphNode[] {
  const phases = phasesFromManifest(detail?.manifest, skillId)
  return phases.map((phase, index) => ({
    id: phase.name,
    type: 'skill',
    position: { x: 160 + (index % 2) * 320, y: 80 + index * 150 },
    data: {
      label: phase.name,
      mode: phase.mode,
      role: phase.mode === 'llm' ? phase.llm_role : 'Logic',
      status: index === 0 ? 'success' : 'idle',
      dependsOn: normalizeDependsOn(phase.depends_on),
      subgraphPath: phase.subgraph ?? null,
    },
  }))
}

function buildEdges(nodes: SkillGraphNode[]): Edge[] {
  return nodes.flatMap((node, index) => {
    const dependencies = node.data.dependsOn.length > 0
      ? node.data.dependsOn
      : index > 0
        ? [nodes[index - 1].id]
        : []

    return dependencies.map((source) => ({
      id: `${source}->${node.id}`,
      source,
      target: node.id,
      type: 'smoothstep',
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { strokeWidth: 1.5 },
    }))
  })
}

export function GraphCanvas({ skillId, skillDetail, isLoading = false, error, selectedNodeId, onNodeSelect }: GraphCanvasProps) {
  const initialNodes = useMemo(() => buildNodes(skillId, skillDetail), [skillDetail, skillId])
  const initialEdges = useMemo(() => buildEdges(initialNodes), [initialNodes])
  const [nodes, setNodes, onNodesChange] = useNodesState<SkillGraphNode>(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
  }, [initialEdges, initialNodes, setEdges, setNodes])

  const selectedNodes = useMemo(
    () => nodes.map((node) => ({ ...node, selected: node.id === selectedNodeId })),
    [nodes, selectedNodeId],
  )

  const onConnect = useCallback((connection: Connection) => {
    setEdges((current) => addEdge({ ...connection, type: 'smoothstep', markerEnd: { type: MarkerType.ArrowClosed } }, current))
  }, [setEdges])

  return (
    <section className="relative h-full min-h-0 bg-background">
      <div className="absolute left-4 top-4 z-10 rounded-md border border-border bg-card px-3 py-2 shadow-sm">
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Edit graph</div>
        <div className="text-sm font-semibold text-foreground">{skillDetail?.manifest.name ?? skillId}</div>
      </div>

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

      <ReactFlow
        nodes={selectedNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={(_, node) => onNodeSelect?.(node.id)}
        fitView
        minZoom={0.35}
        maxZoom={1.4}
      >
        <Background gap={18} size={1} />
        <Controls position="bottom-left" />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </section>
  )
}
