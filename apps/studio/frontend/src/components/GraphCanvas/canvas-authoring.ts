import type { GraphPhaseMode, SerializableGraphPhaseRef, SkillDetail } from '@/api/types'
import { INPUT_ID, OUTPUT_ID } from '@/components/nodes'
import { parsePhaseFrontmatter } from '../studio/panels/phase-frontmatter'
import yaml from 'js-yaml'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'

export type NewPhaseKind = GraphPhaseMode

export interface PhaseDraft {
  phaseId: string
  filePath: string
  fileContent: string
  phaseRef: SerializableGraphPhaseRef
  phases: SerializableGraphPhaseRef[]
}

export type ConnectPhaseRefsResult =
  | { ok: true; phases: SerializableGraphPhaseRef[] }
  | {
    ok: false
    reason: 'global-node' | 'self-dependency' | 'unknown-phase' | 'duplicate-dependency' | 'missing-dependency'
    message: string
  }

export function phaseRefsFromSkillDetail(detail: SkillDetail | undefined): SerializableGraphPhaseRef[] {
  if (!detail?.manifest) {
    return []
  }
  const version = detail.manifest.schema_version
  if (version !== CURRENT_SCHEMA_VERSION) {
    return []
  }

  const topologyById = new Map((detail.graph_topology ?? []).map((phase) => [phase.id, phase]))
  const phaseIds = (detail.manifest.phases ?? []) as unknown as string[]
  return phaseIds.map((phaseId) => {
    const topology = topologyById.get(phaseId)
    const src = topology?.src ?? `phases/${phaseId}`
    const mode = normalizePhaseMode(topology?.mode) ?? modeFromSrc(src)
    return {
      id: phaseId,
      src,
      depends_on: [...(topology?.depends_on ?? [])],
      mode,
    }
  })
}

export function createPhaseDraft(detail: SkillDetail | undefined, kind: NewPhaseKind): PhaseDraft {
  const phases = phaseRefsFromSkillDetail(detail)
  const phaseId = nextPhaseId(phases.map((phase) => phase.id), basePhaseId(kind))
  const filePath = phaseFilePath(phaseId, kind)
  const phaseRef: SerializableGraphPhaseRef = {
    id: phaseId,
    src: phaseDirectoryPath(phaseId),
    depends_on: [],
    mode: kind,
  }
  return {
    phaseId,
    filePath,
    fileContent: defaultPhaseMarkdown(phaseId, kind),
    phaseRef,
    phases: [...phases, phaseRef],
  }
}

export function connectPhaseRefs(
  detail: SkillDetail | undefined,
  sourceId: string | null | undefined,
  targetId: string | null | undefined,
): ConnectPhaseRefsResult {
  if (!sourceId || !targetId || isGlobalNode(sourceId) || isGlobalNode(targetId)) {
    return { ok: false, reason: 'global-node', message: 'Global input/output nodes cannot be persisted as phase dependencies.' }
  }
  if (sourceId === targetId) {
    return { ok: false, reason: 'self-dependency', message: 'A phase cannot depend on itself.' }
  }

  const phases = phaseRefsFromSkillDetail(detail)
  const source = phases.find((phase) => phase.id === sourceId)
  const target = phases.find((phase) => phase.id === targetId)
  if (!source || !target) {
    return { ok: false, reason: 'unknown-phase', message: 'Both connection endpoints must be phase nodes.' }
  }
  if (target.depends_on.includes(source.id)) {
    return { ok: false, reason: 'duplicate-dependency', message: 'This dependency already exists.' }
  }

  return {
    ok: true,
    phases: phases.map((phase) => (
      phase.id === target.id
        ? { ...phase, depends_on: [...phase.depends_on, source.id] }
        : phase
    )),
  }
}

export function disconnectPhaseRefs(
  detail: SkillDetail | undefined,
  sourceId: string | null | undefined,
  targetId: string | null | undefined,
): ConnectPhaseRefsResult {
  if (!sourceId || !targetId || isGlobalNode(sourceId) || isGlobalNode(targetId)) {
    return { ok: false, reason: 'global-node', message: 'Global input/output edges are derived and cannot be disconnected.' }
  }

  const phases = phaseRefsFromSkillDetail(detail)
  const source = phases.find((phase) => phase.id === sourceId)
  const target = phases.find((phase) => phase.id === targetId)
  if (!source || !target) {
    return { ok: false, reason: 'unknown-phase', message: 'Both edge endpoints must be phase nodes.' }
  }
  if (!target.depends_on.includes(source.id)) {
    return { ok: false, reason: 'missing-dependency', message: 'This edge is not backed by a phase dependency.' }
  }

  return {
    ok: true,
    phases: phases.map((phase) => (
      phase.id === target.id
        ? { ...phase, depends_on: phase.depends_on.filter((dependency) => dependency !== source.id) }
        : phase
    )),
  }
}

/** An edge identified purely by its two phase endpoints. */
export interface EdgeEndpoints {
  source: string | null | undefined
  target: string | null | undefined
}

/**
 * Result of planning an edge reconnect (drag an existing edge endpoint onto a
 * different node). A reconnect is the composition of two atomic depends_on
 * mutations the canvas already supports: remove the old dependency, then add the
 * new one. Both halves flow through the existing disconnect/connect → serialize
 * path, so the serialize contract is unchanged (n2-canvas #8, R4).
 */
export type ReconnectPlan =
  | { ok: true; disconnect: { source: string; target: string }; connect: { source: string; target: string } }
  | { ok: false; reason: 'global-node' | 'self-dependency' | 'no-op'; message: string }

/**
 * Pure planner for a React Flow edge reconnect. Given the old edge and the new
 * connection (either the source or the target endpoint may have moved), decide
 * whether the move is a legal dependency edit and, if so, return the disconnect
 * + connect operations to apply. Endpoint legality against the live graph
 * (unknown phase, duplicate, missing dependency) is re-checked by
 * disconnectPhaseRefs / connectPhaseRefs when the plan is applied, mirroring the
 * onConnect validation reuse.
 */
export function planEdgeReconnect(oldEdge: EdgeEndpoints, newConnection: EdgeEndpoints): ReconnectPlan {
  const oldSource = oldEdge.source
  const oldTarget = oldEdge.target
  const newSource = newConnection.source
  const newTarget = newConnection.target
  if (!oldSource || !oldTarget || !newSource || !newTarget) {
    return { ok: false, reason: 'global-node', message: 'Edge endpoints must be phase nodes to reconnect.' }
  }
  if (
    isGlobalNode(oldSource)
    || isGlobalNode(oldTarget)
    || isGlobalNode(newSource)
    || isGlobalNode(newTarget)
  ) {
    return { ok: false, reason: 'global-node', message: 'Global input/output edges are derived and cannot be reconnected.' }
  }
  if (newSource === newTarget) {
    return { ok: false, reason: 'self-dependency', message: 'A phase cannot depend on itself.' }
  }
  if (oldSource === newSource && oldTarget === newTarget) {
    return { ok: false, reason: 'no-op', message: 'Edge was reconnected to the same endpoints.' }
  }

  return {
    ok: true,
    disconnect: { source: oldSource, target: oldTarget },
    connect: { source: newSource, target: newTarget },
  }
}

export function phaseFilePath(phaseId: string, kind: NewPhaseKind): string {
  if (kind === 'skill') {
    return `phases/${phaseId}/SKILL.md`
  }
  if (kind === 'subgraph') {
    return `phases/${phaseId}/SUBGRAPH.md`
  }
  return `phases/${phaseId}/LOGIC.md`
}

function phaseDirectoryPath(phaseId: string): string {
  return `phases/${phaseId}`
}

// Node type is determined by the phase FILE KIND (LOGIC.md / SKILL.md /
// SUBGRAPH.md), never a `mode:` frontmatter field. The scaffolds below stay
// FROZEN-clean per engine skill-syntax §2.3 (LOGIC), §2.5 (agent SKILL),
// §2.4/§2.1 (SUBGRAPH) so the engine compiler accepts them with no
// unknown-field FATAL. Deprecated fields (`mode`, `system_prompt`,
// `exit_contract`, `python_callable`, legacy registry child-reference fields)
// must never be emitted.
const SUBGRAPH_PATH_PLACEHOLDER = '/absolute/path/to/child_skill'

export function defaultPhaseMarkdown(
  phaseId: string,
  kind: NewPhaseKind,
  subgraphPath = SUBGRAPH_PATH_PLACEHOLDER,
): string {
  if (kind === 'skill') {
    return agentPhaseMarkdown(phaseId)
  }
  if (kind === 'subgraph') {
    return subgraphPhaseMarkdown(phaseId, subgraphPath)
  }
  return logicPhaseMarkdown(phaseId)
}

function logicPhaseMarkdown(phaseId: string): string {
  const actionName = `${phaseId.replaceAll('-', '_')}_action`
  return [
    '---',
    `name: ${phaseId}`,
    'io:',
    '  inputs:',
    '    type: object',
    '    properties: {}',
    '  outputs:',
    '    type: object',
    '    properties: {}',
    `actions: [${actionName}]`,
    'validator: false',
    '---',
    '',
    `<action>${actionName}</action>`,
    '',
  ].join('\n')
}

function agentPhaseMarkdown(phaseId: string): string {
  return [
    '---',
    `name: ${phaseId}`,
    'llm_role: analyst',
    'io:',
    '  inputs:',
    '    type: object',
    '    properties: {}',
    '  outputs:',
    '    type: object',
    '    properties: {}',
    'tools: []',
    'validator: false',
    '---',
    '',
    '<role>',
    `Describe the professional identity ${phaseId} should adopt.`,
    '</role>',
    '',
    '<goal>',
    `Describe what ${phaseId} must produce, then call finish_task.`,
    '</goal>',
    '',
    '<step id="S1" name="plan">Outline the approach before acting.</step>',
    '',
    '<protocol id="P1">State the rule each key judgement relies on.</protocol>',
    '',
  ].join('\n')
}

function subgraphPhaseMarkdown(phaseId: string, subgraphPath: string): string {
  return [
    '---',
    `name: ${phaseId}`,
    `path: ${subgraphPath}`,
    'io:',
    '  inputs:',
    '    type: object',
    '    properties: {}',
    '  outputs:',
    '    type: object',
    '    properties: {}',
    'validator: false',
    '---',
    '',
  ].join('\n')
}

function nextPhaseId(existingIds: string[], base: string): string {
  const existing = new Set(existingIds)
  if (!existing.has(base)) {
    return base
  }
  let suffix = 2
  while (existing.has(`${base}-${suffix}`)) {
    suffix += 1
  }
  return `${base}-${suffix}`
}

function basePhaseId(kind: NewPhaseKind): string {
  if (kind === 'skill') {
    return 'agent'
  }
  return kind
}

function modeFromSrc(src: string): GraphPhaseMode {
  if (src.endsWith('/SKILL.md')) {
    return 'skill'
  }
  if (src.endsWith('/SUBGRAPH.md')) {
    return 'subgraph'
  }
  return 'logic'
}

function normalizePhaseMode(mode: string | undefined): GraphPhaseMode | null {
  if (mode === 'skill' || mode === 'subgraph' || mode === 'logic') {
    return mode
  }
  return null
}

function isGlobalNode(id: string): boolean {
  return id === INPUT_ID || id === OUTPUT_ID
}

export interface OverwriteConflict {
  nodeId: string
  fieldName: string
  ancestorNodeId: string
}

export function checkSequentialOverwrites(
  skillDetail: SkillDetail | undefined,
  phases: SerializableGraphPhaseRef[],
): OverwriteConflict[] {
  if (!skillDetail?.files) {
    return []
  }

  const phaseMap = new Map<string, SerializableGraphPhaseRef>()
  for (const phase of phases) {
    phaseMap.set(phase.id, phase)
  }

  const getTransitiveAncestors = (phaseId: string): Set<string> => {
    const ancestors = new Set<string>()
    const queue = [...(phaseMap.get(phaseId)?.depends_on ?? [])]
    while (queue.length > 0) {
      const current = queue.shift()!
      if (!ancestors.has(current)) {
        ancestors.add(current)
        const parent = phaseMap.get(current)
        if (parent) {
          queue.push(...parent.depends_on)
        }
      }
    }
    return ancestors
  }

  const getPhaseOutputsAndWhitelist = (phaseId: string): { outputs: string[]; whitelist: string[] } => {
    const phase = phaseMap.get(phaseId)
    if (!phase) {
      return { outputs: [], whitelist: [] }
    }
    const relativePath = phaseFilePath(phaseId, phase.mode)
    const fileContent = skillDetail.files?.[relativePath]
    if (!fileContent) {
      return { outputs: [], whitelist: [] }
    }

    const parsed = parsePhaseFrontmatter(fileContent)
    if (!parsed.ok) {
      return { outputs: [], whitelist: [] }
    }

    const fm = parsed.frontmatter
    const io = typeof fm.io === 'object' && fm.io !== null && !Array.isArray(fm.io)
      ? (fm.io as Record<string, unknown>)
      : null
    const ioOutputs = io?.outputs && typeof io.outputs === 'object' && !Array.isArray(io.outputs)
      ? (io.outputs as Record<string, unknown>)
      : null
    const properties = ioOutputs?.properties && typeof ioOutputs.properties === 'object' && !Array.isArray(ioOutputs.properties)
      ? (ioOutputs.properties as Record<string, unknown>)
      : null
    const outputs = properties ? Object.keys(properties) : []
    const whitelist = Array.isArray(fm.allow_sequential_overwrite)
      ? (fm.allow_sequential_overwrite as string[])
      : []

    return { outputs, whitelist }
  }

  const conflicts: OverwriteConflict[] = []
  const phaseDataMap = new Map<string, { outputs: string[]; whitelist: string[] }>()
  for (const phase of phases) {
    phaseDataMap.set(phase.id, getPhaseOutputsAndWhitelist(phase.id))
  }

  for (const phase of phases) {
    const { outputs, whitelist } = phaseDataMap.get(phase.id) ?? { outputs: [], whitelist: [] }
    if (outputs.length === 0) {
      continue
    }

    const ancestors = getTransitiveAncestors(phase.id)
    for (const ancestorId of ancestors) {
      const ancestorData = phaseDataMap.get(ancestorId)
      if (!ancestorData) {
        continue
      }

      for (const fieldName of outputs) {
        if (ancestorData.outputs.includes(fieldName) && !whitelist.includes(fieldName)) {
          const alreadyExists = conflicts.some(
            (c) => c.nodeId === phase.id && c.fieldName === fieldName && c.ancestorNodeId === ancestorId,
          )
          if (!alreadyExists) {
            conflicts.push({
              nodeId: phase.id,
              fieldName,
              ancestorNodeId: ancestorId,
            })
          }
        }
      }
    }
  }

  return conflicts
}

export function addSequentialOverwriteField(
  markdown: string,
  fieldName: string,
): string {
  const parsed = parsePhaseFrontmatter(markdown)
  if (!parsed.ok) return markdown
  const fm = parsed.frontmatter
  const whitelist = Array.isArray(fm.allow_sequential_overwrite)
    ? [...(fm.allow_sequential_overwrite as string[])]
    : []
  if (!whitelist.includes(fieldName)) {
    whitelist.push(fieldName)
  }
  fm.allow_sequential_overwrite = whitelist

  const dumped = yaml.dump(fm, {
    lineWidth: 120,
    noRefs: true,
    sortKeys: false,
    styles: { '!!null': 'empty' },
  }).trimEnd()
  const body = parsed.body.length > 0 ? `\n${parsed.body}` : '\n'
  return `---\n${dumped}\n---${body}`
}
