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
import yaml from 'js-yaml'
import { toast } from 'sonner'
import type { IoDeclaration, PhaseDef, SkillDetail, SkillManifest } from '@/api/types'
import { CycleDetectedError, getAutoLayoutedElements } from '@/lib/layout'
import { ContextEdge, type ContextEdgeData } from '@/components/edges/ContextEdge'
import { GlobalInputNode, GlobalOutputNode } from '@/components/nodes/GlobalInputOutputNode'
import { buildEdges, INPUT_ID, OUTPUT_ID, SkillNode, type GlobalNodeData, type GraphCanvasNode, type SkillGraphNode, type SkillGraphNodeData, type SkillNodeStatus, type SubagentRef } from '@/components/nodes'
import { useOptionalWorkspaceContext } from '@/components/studio/WorkspaceContext'
import type { PanelKind } from '@/components/studio/Toolbar'

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

const EMPTY_IO: IoDeclaration = { inputs: [], outputs: [] }

function phaseKindFile(data: Pick<SkillGraphNodeData, 'mode' | 'subgraphPath'>): 'LOGIC.md' | 'SKILL.md' | 'SUBGRAPH.md' {
  if (data.subgraphPath || data.mode === 'subgraph') return 'SUBGRAPH.md'
  if (data.mode === 'skill' || data.mode === 'llm') return 'SKILL.md'
  return 'LOGIC.md'
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
