import yaml from 'js-yaml'
import type { IoDeclaration, PhaseDef, SkillDetail, SkillManifest, IoInput, IoOutput, GraphManifestV030 } from '@/api/types'
import { INPUT_ID, OUTPUT_ID, type GlobalNodeData, type GraphCanvasNode, type SkillGraphNode, type SkillGraphNodeData, type SkillNodeStatus, type SubagentRef } from '@/components/nodes'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'

const EMPTY_IO: IoDeclaration = { inputs: [], outputs: [] }

export function phaseKindFile(data: Pick<SkillGraphNodeData, 'mode' | 'subgraphPath'>): 'LOGIC.md' | 'SKILL.md' | 'SUBGRAPH.md' {
  if (data.subgraphPath || data.mode === 'subgraph') return 'SUBGRAPH.md'
  if (data.mode === 'agent' || data.mode === 'skill' || data.mode === 'llm') return 'SKILL.md'
  return 'LOGIC.md'
}

function normalizeDependsOn(value: string | string[] | undefined): string[] {
  if (Array.isArray(value)) {
    return value.filter(Boolean)
  }
  return value ? [value] : []
}

function phasesFromManifest(manifest: SkillManifest | undefined, skillId: string): PhaseDef[] {
  if (manifest?.schema_version === CURRENT_SCHEMA_VERSION) {
    const phaseList = (manifest.phases as unknown as string[]).map((phaseId) => ({ id: phaseId, depends_on: [] }))

    return phaseList.map((phase) => ({
      name: phase.id,
      mode: 'logic',
      model_override: null,
      depends_on: phase.depends_on ?? [],
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
  if (manifest?.schema_version === CURRENT_SCHEMA_VERSION) {
    const io = (manifest as GraphManifestV030).io
    const inputs: IoInput[] = io?.inputs?.properties
      ? Object.keys(io.inputs.properties).map((name) => ({ name, type: 'string', source: 'runtime', default: null }))
      : []
    const outputs: IoOutput[] = io?.outputs?.properties
      ? Object.keys(io.outputs.properties).map((name) => ({ name, type: 'string', target: 'file', path: null }))
      : []
    return { inputs, outputs }
  }
  return manifest?.type === 'graph' ? manifest.io : EMPTY_IO
}

function subgraphRefFromFile(content: string | undefined): string | null {
  if (!content) return null
  const block = content.match(/<target_skill>\s*([\s\S]*?)\s*<\/target_skill>/)
  if (block?.[1]) return block[1].trim()
  const yaml = content.match(/^target_skill:\s*['"]?([^'"\n]+)['"]?/m)
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

function stringListFromUnknown(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

export function buildNodes(
  skillId: string,
  detail: SkillDetail | undefined,
  expandedSubgraphs: Set<string>,
  onToggleSubgraph: (nodeId: string) => void,
  statusByNodeId: Record<string, SkillNodeStatus>,
): GraphCanvasNode[] {
  const phases = phasesFromManifest(detail?.manifest, skillId)
  const io = ioFromManifest(detail?.manifest)
  const topologyById = new Map((detail?.graph_topology ?? []).map((phase) => [phase.id, phase]))
  const phaseNodes: SkillGraphNode[] = phases.map((phase, index) => {
    const topology = topologyById.get(phase.name)
    const mode = topology?.mode ?? phase.mode
    const subgraphPath = phase.subgraph ?? subgraphRefFromFile(detail?.files?.[`phases/${phase.name}/SUBGRAPH.md`])
    const filePath = `phases/${phase.name}/${phaseKindFile({ mode, subgraphPath })}`
    const frontmatter = phaseFrontmatter(detail?.files?.[filePath])
    return {
      id: phase.name,
      type: 'skill',
      position: { x: 160 + (index % 2) * 320, y: 80 + index * 150 },
      data: {
        label: phase.name,
        mode,
        role: phase.mode === 'llm' ? phase.llm_role : null,
        tools: mode === 'skill' ? stringListFromUnknown(frontmatter?.tools) : phase.mode === 'llm' ? phase.agent_tools : [],
        subagents: subagentsForPhase(detail, phase.name),
        filePath,
        status: statusByNodeId[phase.name] ?? 'idle',
        dependsOn: topology?.depends_on ?? normalizeDependsOn(phase.depends_on),
        subgraphPath,
        isExpanded: expandedSubgraphs.has(phase.name),
        onToggleSubgraph: (phase.subgraph ?? detail?.files?.[`phases/${phase.name}/SUBGRAPH.md`])
          ? () => onToggleSubgraph(phase.name)
          : undefined,
      },
    }
  })
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
