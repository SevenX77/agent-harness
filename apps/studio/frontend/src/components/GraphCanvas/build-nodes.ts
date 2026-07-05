import yaml from 'js-yaml'
import type { CompileError, GraphManifestV030, GraphTopologyItem, IoDeclaration, IoInput, IoOutput, PhaseDef, SkillDetail, SkillManifest } from '@/api/types'
import { INPUT_ID, OUTPUT_ID, type GlobalNodeData, type GraphCanvasNode, type SkillGraphNode, type SkillGraphNodeData, type SkillNodeStatus, type SubagentRef } from '@/components/nodes'
import { normalizeSubgraphPath } from '@/components/studio/subgraph-path'
import type { GoldenNodeState } from '@/components/studio/node-golden'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'

const EMPTY_IO: IoDeclaration = { inputs: [], outputs: [] }

export function phaseKindFile(data: Pick<SkillGraphNodeData, 'mode' | 'subgraphPath'>): 'LOGIC.md' | 'SKILL.md' | 'SUBGRAPH.md' {
  if (data.subgraphPath || data.mode === 'subgraph') return 'SUBGRAPH.md'
  if (data.mode === 'agent' || data.mode === 'skill' || data.mode === 'llm') return 'SKILL.md'
  return 'LOGIC.md'
}

// Node KIND is owned by the physical phase FILE that exists in the phase
// directory — SUBGRAPH.md / SKILL.md / LOGIC.md — never an author-writable
// `mode:` frontmatter field (engine `_reject_phase_forbidden_metadata` rejects
// it). This mirrors the engine's `_PHASE_FILE_TO_MODE` projection on the FE so a
// stale `topology.mode` can never override the kind the file on disk declares.
// Returns null when none of the three node files is present, so callers fall back
// to the topology mode (and a 'logic' default) — but NEVER to the manifest-
// projected `phase.mode`, which would re-open the F1 ambiguity (atom #16).
function phaseModeFromFiles(
  phaseId: string,
  files: SkillDetail['files'] | undefined,
): SkillGraphNodeData['mode'] | null {
  if (!files) return null
  if (files[`phases/${phaseId}/SUBGRAPH.md`] !== undefined) return 'subgraph'
  if (files[`phases/${phaseId}/SKILL.md`] !== undefined) return 'agent'
  if (files[`phases/${phaseId}/LOGIC.md`] !== undefined) return 'logic'
  return null
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
  // Editor content can be mid-edit / malformed (js-yaml's load() throws on e.g. a
  // duplicate mapping key); degrade to null instead of throwing through canvas render.
  let parsed: unknown
  try {
    parsed = yaml.load(match[1])
  } catch {
    return null
  }
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

// Tools for an AGENT node come from the SKILL.md frontmatter `tools:` list (the
// file on disk is the source of truth in the editor). `isSkillFile` is true for
// the whole agent family (mode agent/skill/llm -> SKILL.md, see phaseKindFile);
// the engine projects an agent phase's mode as 'agent' (never 'skill'), so the
// old `mode === 'skill'` guard was dead and agent tools never rendered. Fall
// back to the manifest `agent_tools` (legacy standalone-agent skills, mode 'llm')
// only when the frontmatter declares none.
function toolsForPhase(
  isSkillFile: boolean,
  frontmatter: Record<string, unknown> | null,
  phase: PhaseDef,
): string[] {
  if (!isSkillFile) return []
  const frontmatterTools = stringListFromUnknown(frontmatter?.tools)
  if (frontmatterTools.length > 0) return frontmatterTools
  return phase.mode === 'llm' ? phase.agent_tools : []
}

// N2 atom #15 (l3-step-edit): the canvas-owned inputs that mount the inline L3
// step editor onto AGENT nodes. Grouped into one object so buildNodes' positional
// signature (already at its limit) does not grow further. All optional so existing
// callers / the drilled-child path render unchanged when steps editing is not wired.
export interface AgentStepsInputs {
  expandedSteps?: Set<string>
  onToggleSteps?: (nodeId: string) => void
  // Persist an edited agent body. The canvas binds the file path + the
  // optimistic-lock hash (of the pre-edit body) and this forwards the result.
  onStepsSave?: (nodeId: string, filePath: string, currentBody: string, nextBody: string) => void
  // N5 atom #3 (dirty-downstream-graying): the `affected_downstream` node ids the
  // resume-validity endpoint returned for the node being resumed from. Each node
  // in this set is grayed (its node-level Resume can't continue); unrelated
  // branches are absent and stay normal. Carried here so buildNodes' positional
  // signature (already at its limit) does not grow further.
  dirtyDownstreamNodeIds?: ReadonlySet<string>
}

export function buildNodes(
  skillId: string,
  detail: SkillDetail | undefined,
  expandedSubgraphs: Set<string>,
  onToggleSubgraph: (nodeId: string) => void,
  statusByNodeId: Record<string, SkillNodeStatus>,
  compileErrorsByNodeId: Record<string, CompileError[]> = {},
  goldenStateByNodeId: Record<string, GoldenNodeState> = {},
  errorMessageByNodeId: Record<string, string> = {},
  agentSteps: AgentStepsInputs = {},
  workspaceRoot: string | null = null,
): GraphCanvasNode[] {
  const phases = phasesFromManifest(detail?.manifest, skillId)
  const io = ioFromManifest(detail?.manifest)
  const topologyById = new Map((detail?.graph_topology ?? []).map((phase) => [phase.id, phase]))
  const phaseNodes: SkillGraphNode[] = phases.map((phase, index) => {
    const topology = topologyById.get(phase.name)
    // N2 atom #16 (node-type-derivation, F1): node KIND derives strictly from
    // FILE EXISTENCE (which SKILL/LOGIC/SUBGRAPH.md is on disk), falling back to
    // the engine-injected `topology.mode` (itself file-derived via
    // `_PHASE_FILE_TO_MODE`) only when no node file is loaded, and to the 'logic'
    // default when neither exists. The manifest-projected `phase.mode` is NEVER a
    // fallback for the kind — trusting it would let a stale/mutable manifest mode
    // override the file truth (the F1 ambiguity). This mirrors the drilled-child
    // path's `phaseKindFromTopologyMode(topology?.mode)`.
    const mode = phaseModeFromFiles(phase.name, detail?.files) ?? phaseKindFromTopologyMode(topology?.mode)
    const subgraphPath = normalizeSubgraphPath(topology?.path)
    const filePath = `phases/${phase.name}/${phaseKindFile({ mode, subgraphPath })}`
    const frontmatter = phaseFrontmatter(detail?.files?.[filePath])
    // N2 atom #15: AGENT nodes (SKILL.md) get the inline L3 step editor wired off
    // the real on-disk body. Non-agent (logic/subgraph) nodes leave it undefined.
    const isAgentNode = phaseKindFile({ mode, subgraphPath }) === 'SKILL.md'
    const agentBody = isAgentNode ? detail?.files?.[filePath] : undefined
    const { onToggleSteps, onStepsSave } = agentSteps
    return {
      id: phase.name,
      type: 'skill',
      position: { x: 160 + (index % 2) * 320, y: 80 + index * 150 },
      data: {
        skillId,
        workspaceRoot,
        phaseId: phase.name,
        label: phase.name,
        mode,
        role: phase.mode === 'llm' ? phase.llm_role : null,
        tools: toolsForPhase(isAgentNode, frontmatter, phase),
        subagents: subagentsForPhase(detail, phase.name),
        filePath,
        status: statusByNodeId[phase.name] ?? 'idle',
        errorMessage: errorMessageByNodeId[phase.name],
        compileErrors: compileErrorsByNodeId[phase.name] ?? [],
        goldenState: goldenStateByNodeId[phase.name],
        // N5 atom #3: gray this node when it is in the resume's affected-downstream set.
        isDirtyDownstream: agentSteps.dirtyDownstreamNodeIds?.has(phase.name) ?? false,
        dependsOn: topology?.depends_on ?? normalizeDependsOn(phase.depends_on),
        isOutput: topology?.output === true,
        subgraphPath,
        isExpanded: expandedSubgraphs.has(phase.name),
        // Every SUBGRAPH-kind node gets the expand toggle — including ones whose
        // path is unresolved/missing (subgraphPath null). Expanding an unresolved
        // node surfaces the recovery state inline (F4: "unresolved path shows
        // recovery state"); gating on a resolved path is what made the "+" vanish
        // from such nodes (PM 2026-06-23).
        onToggleSubgraph: mode === 'subgraph'
          ? () => onToggleSubgraph(phase.name)
          : undefined,
        agentBody,
        isStepsExpanded: isAgentNode ? (agentSteps.expandedSteps?.has(phase.name) ?? false) : false,
        onToggleSteps: isAgentNode && onToggleSteps
          ? () => onToggleSteps(phase.name)
          : undefined,
        onStepsSave: isAgentNode && onStepsSave && agentBody !== undefined
          ? (nextBody: string) => onStepsSave(phase.name, filePath, agentBody, nextBody)
          : undefined,
      },
    }
  })
  return [
    {
      id: INPUT_ID,
      type: 'globalInput',
      position: { x: 0, y: 0 },
      data: { type: 'global-input', schema: io, skillId, workspaceRoot, compileErrors: compileErrorsByNodeId[INPUT_ID] ?? [] } satisfies GlobalNodeData,
    },
    ...phaseNodes,
    {
      id: OUTPUT_ID,
      type: 'globalOutput',
      position: { x: 0, y: 0 },
      data: { type: 'global-output', schema: io, skillId, workspaceRoot, compileErrors: compileErrorsByNodeId[OUTPUT_ID] ?? [] } satisfies GlobalNodeData,
    },
  ]
}

function phaseKindFromTopologyMode(mode: string | undefined): SkillGraphNodeData['mode'] {
  return mode ?? 'logic'
}

/**
 * Build canvas nodes for a DRILLED child graph (R9 subgraph drill-down).
 *
 * Unlike `buildNodes` (which derives phases from a SkillDetail manifest + phase
 * files), the drilled child only exposes its resolved `phases` (ordering/
 * presence source of truth) and `graph_topology` rows (per-phase mode / deps /
 * nested subgraph path). We map each into the same SkillGraphNode shape so the
 * existing buildEdges + auto-layout pipeline renders it identically, and so a
 * NESTED subgraph phase still exposes its `subgraphPath` for deeper drilling.
 *
 * No file frontmatter is available at this depth, so tools/subagents/role are
 * left empty — the drilled view shows real phase topology, not the editor-only
 * file-derived enrichments. The per-phase `filePath`, however, IS derived (from
 * the resolved topology mode via `phaseKindFile`): it is the path to the node's
 * source file RELATIVE TO THE CHILD SUBGRAPH'S OWN ROOT, so that drilling into
 * the child as its own skill and opening this file lands on the child's real
 * `phases/<id>/{SKILL,LOGIC,SUBGRAPH}.md` (closing the drill-edit write-back
 * loop) instead of a stale `undefined` that would resolve against the parent.
 */
export function buildNodesFromTopology(
  skillId: string,
  phases: string[],
  graphTopology: GraphTopologyItem[],
  statusByNodeId: Record<string, SkillNodeStatus>,
  agentSteps: AgentStepsInputs = {},
  workspaceRoot: string | null = null,
): GraphCanvasNode[] {
  const io = EMPTY_IO
  const topologyById = new Map(graphTopology.map((row) => [row.id, row]))
  const phaseNodes: SkillGraphNode[] = phases.map((phaseName, index) => {
    const topology = topologyById.get(phaseName)
    const mode = phaseKindFromTopologyMode(topology?.mode)
    const subgraphPath = normalizeSubgraphPath(topology?.path)
    const filePath = `phases/${phaseName}/${phaseKindFile({ mode, subgraphPath })}`
    // n2-canvas #14: the topology-only (drill loading / fallback) view has no file
    // body, so the AGENT step-editor open/close toggle is wired but the body-bound
    // save (onStepsSave / agentBody) is not — that is supplied by the Option-A
    // loaded path (buildNodes with the child's full SkillDetail). The toggle is
    // withheld entirely on the read-only/compact projection (agentSteps left {}).
    const isAgentNode = phaseKindFile({ mode, subgraphPath }) === 'SKILL.md'
    const { onToggleSteps } = agentSteps
    return {
      id: phaseName,
      type: 'skill',
      position: { x: 160 + (index % 2) * 320, y: 80 + index * 150 },
      data: {
        skillId,
        workspaceRoot,
        phaseId: phaseName,
        label: phaseName,
        mode,
        role: null,
        tools: [],
        subagents: [],
        filePath,
        status: statusByNodeId[phaseName] ?? 'idle',
        dependsOn: topology?.depends_on ?? [],
        isOutput: topology?.output === true,
        subgraphPath,
        isExpanded: false,
        onToggleSubgraph: undefined,
        isStepsExpanded: isAgentNode ? (agentSteps.expandedSteps?.has(phaseName) ?? false) : false,
        onToggleSteps: isAgentNode && onToggleSteps
          ? () => onToggleSteps(phaseName)
          : undefined,
      },
    }
  })
  return [
    {
      id: INPUT_ID,
      type: 'globalInput',
      position: { x: 0, y: 0 },
      data: { type: 'global-input', schema: io, skillId, workspaceRoot } satisfies GlobalNodeData,
    },
    ...phaseNodes,
    {
      id: OUTPUT_ID,
      type: 'globalOutput',
      position: { x: 0, y: 0 },
      data: { type: 'global-output', schema: io, skillId, workspaceRoot } satisfies GlobalNodeData,
    },
  ]
}
