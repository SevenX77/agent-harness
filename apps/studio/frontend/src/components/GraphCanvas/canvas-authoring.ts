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
    reason: 'invalid-endpoint' | 'self-dependency' | 'unknown-phase' | 'duplicate-dependency' | 'missing-dependency'
    message: string
  }

export type RemovePhaseRefsResult =
  | { ok: true; phases: SerializableGraphPhaseRef[] }
  | {
    ok: false
    reason: 'invalid-phase' | 'unknown-phase'
    message: string
  }

export type RenamePhaseRefsResult =
  | { ok: true; phases: SerializableGraphPhaseRef[] }
  | {
    ok: false
    reason: 'invalid-phase' | 'unknown-phase' | 'duplicate-phase' | 'unchanged'
    message: string
  }

const PHASE_ID_PATTERN = /^[A-Za-z_][A-Za-z0-9_-]*$/

export function isSafePhaseId(value: string): boolean {
  const trimmed = value.trim()
  return trimmed.length > 0 && trimmed.length <= 100 && PHASE_ID_PATTERN.test(trimmed)
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
      depends_on: serializableDependsOn(topology?.depends_on ?? []),
      ...(topology?.output === true ? { output: true } : {}),
      mode,
    }
  })
}

export function phaseDirectoryIdsFromSkillDetail(detail: SkillDetail | undefined): string[] {
  if (!detail?.files) {
    return []
  }

  const ids = new Set<string>()
  for (const path of Object.keys(detail.files)) {
    const normalized = path.replaceAll("\\", "/")
    const match = /^phases\/([^/]+)(?:\/|$)/.exec(normalized)
    const phaseId = match?.[1]
    if (phaseId && isSafePhaseId(phaseId)) {
      ids.add(phaseId)
    }
  }
  return [...ids].sort()
}

export function orphanPhaseDirectoryIds(
  detail: SkillDetail | undefined,
  nextPhases: SerializableGraphPhaseRef[],
): string[] {
  const activeIds = new Set(nextPhases.map((phase) => phase.id))
  return phaseDirectoryIdsFromSkillDetail(detail).filter((phaseId) => !activeIds.has(phaseId))
}

export function defaultPhaseId(
  detail: SkillDetail | undefined,
  kind: NewPhaseKind,
  reservedPhaseIds: Iterable<string> = [],
): string {
  const phases = phaseRefsFromSkillDetail(detail)
  return nextPhaseId(
    [
      ...phases.map((phase) => phase.id),
      ...phaseDirectoryIdsFromSkillDetail(detail),
      ...reservedPhaseIds,
    ],
    basePhaseId(kind),
  )
}

export function phaseNameError(
  phaseId: string,
  detail: SkillDetail | undefined,
  reservedPhaseIds: Iterable<string> = [],
): string | null {
  const trimmed = phaseId.trim()
  if (!trimmed) {
    return 'Phase name is required.'
  }
  if (!isSafePhaseId(trimmed)) {
    return 'Phase names must start with a letter or underscore and contain only letters, numbers, underscores, or hyphens.'
  }
  const existingIds = new Set([
    ...phaseRefsFromSkillDetail(detail).map((phase) => phase.id),
    ...phaseDirectoryIdsFromSkillDetail(detail),
    ...reservedPhaseIds,
  ])
  if (existingIds.has(trimmed)) {
    return `A phase named ${trimmed} already exists.`
  }
  return null
}

export function createPhaseDraft(
  detail: SkillDetail | undefined,
  kind: NewPhaseKind,
  reservedPhaseIds: Iterable<string> = [],
  requestedPhaseId?: string,
): PhaseDraft {
  const phases = phaseRefsFromSkillDetail(detail)
  const phaseId = requestedPhaseId?.trim() || defaultPhaseId(detail, kind, reservedPhaseIds)
  const error = requestedPhaseId ? phaseNameError(phaseId, detail, reservedPhaseIds) : null
  if (error) {
    throw new Error(error)
  }
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
  if (!sourceId || !targetId) {
    return { ok: false, reason: 'invalid-endpoint', message: 'Both connection endpoints must be phase nodes.' }
  }
  if (sourceId === targetId) {
    return { ok: false, reason: 'self-dependency', message: 'A phase cannot depend on itself.' }
  }

  const phases = phaseRefsFromSkillDetail(detail)
  if (sourceId === INPUT_ID) {
    const target = phases.find((phase) => phase.id === targetId)
    if (!target) {
      return { ok: false, reason: 'unknown-phase', message: 'Graph input must connect to a phase node.' }
    }
    if (target.depends_on.includes('input')) {
      return { ok: false, reason: 'duplicate-dependency', message: 'This dependency already exists.' }
    }
    return {
      ok: true,
      phases: phases.map((phase) => (
        phase.id === target.id
          ? { ...phase, depends_on: [...phase.depends_on, 'input'] }
          : phase
      )),
    }
  }
  if (targetId === OUTPUT_ID) {
    const source = phases.find((phase) => phase.id === sourceId)
    if (!source) {
      return { ok: false, reason: 'unknown-phase', message: 'Graph output must be connected from a phase node.' }
    }
    if (source.output === true) {
      return { ok: false, reason: 'duplicate-dependency', message: 'This output marker already exists.' }
    }
    return {
      ok: true,
      phases: phases.map((phase) => (
        phase.id === source.id ? { ...phase, output: true } : phase
      )),
    }
  }
  if (sourceId === OUTPUT_ID || targetId === INPUT_ID) {
    return { ok: false, reason: 'invalid-endpoint', message: 'Graph boundaries must connect as Input -> phase or phase -> Output.' }
  }

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
  if (!sourceId || !targetId) {
    return { ok: false, reason: 'invalid-endpoint', message: 'Both edge endpoints must be phase nodes.' }
  }

  const phases = phaseRefsFromSkillDetail(detail)
  if (sourceId === INPUT_ID) {
    const target = phases.find((phase) => phase.id === targetId)
    if (!target) {
      return { ok: false, reason: 'unknown-phase', message: 'Graph input must disconnect from a phase node.' }
    }
    if (!target.depends_on.includes('input')) {
      return { ok: false, reason: 'missing-dependency', message: 'This edge is not backed by a graph input dependency.' }
    }
    return {
      ok: true,
      phases: phases.map((phase) => (
        phase.id === target.id
          ? { ...phase, depends_on: phase.depends_on.filter((dependency) => dependency !== 'input') }
          : phase
      )),
    }
  }
  if (targetId === OUTPUT_ID) {
    const source = phases.find((phase) => phase.id === sourceId)
    if (!source) {
      return { ok: false, reason: 'unknown-phase', message: 'Graph output must disconnect from a phase node.' }
    }
    if (source.output !== true) {
      return { ok: false, reason: 'missing-dependency', message: 'This edge is not backed by an output marker.' }
    }
    return {
      ok: true,
      phases: phases.map((phase) => {
        if (phase.id !== source.id) return phase
        const nextPhase = { ...phase }
        delete nextPhase.output
        return nextPhase
      }),
    }
  }
  if (sourceId === OUTPUT_ID || targetId === INPUT_ID) {
    return { ok: false, reason: 'invalid-endpoint', message: 'Graph boundaries must disconnect as Input -> phase or phase -> Output.' }
  }

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

function serializableDependsOn(dependsOn: readonly string[]): string[] {
  return [...dependsOn]
}

export function removePhaseRefs(
  detail: SkillDetail | undefined,
  phaseId: string | null | undefined,
): RemovePhaseRefsResult {
  if (!phaseId) {
    return { ok: false, reason: 'invalid-phase', message: 'Phase id is required.' }
  }

  const phases = phaseRefsFromSkillDetail(detail)
  if (!phases.some((phase) => phase.id === phaseId)) {
    return { ok: false, reason: 'unknown-phase', message: 'Phase not found.' }
  }

  return {
    ok: true,
    phases: phases
      .filter((phase) => phase.id !== phaseId)
      .map((phase) => ({
        ...phase,
        depends_on: phase.depends_on.filter((dependency) => dependency !== phaseId),
      })),
  }
}

export function renamePhaseRefs(
  detail: SkillDetail | undefined,
  phaseId: string | null | undefined,
  nextPhaseId: string,
): RenamePhaseRefsResult {
  if (!phaseId) {
    return { ok: false, reason: 'invalid-phase', message: 'Select a phase node to rename.' }
  }
  const nextId = nextPhaseId.trim()
  if (!isSafePhaseId(nextId)) {
    return {
      ok: false,
      reason: 'invalid-phase',
      message: 'Phase names must start with a letter or underscore and contain only letters, numbers, underscores, or hyphens.',
    }
  }
  if (nextId === phaseId) {
    return { ok: false, reason: 'unchanged', message: 'Phase name is unchanged.' }
  }

  const phases = phaseRefsFromSkillDetail(detail)
  if (!phases.some((phase) => phase.id === phaseId)) {
    return { ok: false, reason: 'unknown-phase', message: 'The selected phase is not in GRAPH.md.' }
  }
  if (phases.some((phase) => phase.id === nextId)) {
    return { ok: false, reason: 'duplicate-phase', message: `A phase named ${nextId} already exists.` }
  }

  return {
    ok: true,
    phases: phases.map((phase) => {
      const renamed = phase.id === phaseId
      return {
        ...phase,
        id: renamed ? nextId : phase.id,
        src: renamed ? phaseDirectoryPath(nextId) : phase.src,
        depends_on: phase.depends_on.map((dependency) => dependency === phaseId ? nextId : dependency),
      }
    }),
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
  | { ok: false; reason: 'invalid-endpoint' | 'self-dependency' | 'no-op'; message: string }

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
    return { ok: false, reason: 'invalid-endpoint', message: 'Edge endpoints must be phase nodes to reconnect.' }
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

function skillDetailFromPhaseRefs(phases: SerializableGraphPhaseRef[]): SkillDetail {
  return {
    manifest: {
      schema_version: CURRENT_SCHEMA_VERSION,
      name: 'draft',
      description: '',
      io: {
        inputs: { type: 'object', properties: {} },
        outputs: { type: 'object', properties: {} },
      },
      phases: phases.map((phase) => phase.id),
    },
    graph_topology: phases.map((phase) => ({
      id: phase.id,
      src: phase.src,
      depends_on: [...phase.depends_on],
      ...(phase.output === true ? { output: true } : {}),
      mode: phase.mode,
    })),
    node_schema_v21: {},
    io_schema: {},
    file_paths: {},
    files: {},
    manifest_errors: null,
    has_golden: false,
    latest_run_metadata: null,
    lint_result: null,
  }
}

export type ReconnectPhaseRefsResult =
  | { ok: true; phases: SerializableGraphPhaseRef[] }
  | {
    ok: false
    reason: 'invalid-endpoint' | 'self-dependency' | 'unknown-phase' | 'duplicate-dependency' | 'missing-dependency' | 'no-op'
    message: string
  }

/**
 * Compute the next phases for an edge reconnect as a SINGLE atomic depends_on
 * mutation (n2-canvas #8 lost-update fix). The previous implementation ran the
 * disconnect and the connect as TWO sequential serialize round-trips against the
 * same captured skillDetail closure: the disconnect wrote a new GRAPH.md (hash
 * changed) and revalidated, but the queued connect still serialized the
 * PRE-disconnect phases with a now-stale expected_hash, so the backend hash
 * guard rejected it with 409 and left the graph half-mutated.
 *
 * This helper instead derives ONE phases list off a single `phaseRefsFromSkillDetail`
 * snapshot that BOTH drops the old dependency (disconnect.source from
 * disconnect.target) AND adds the new dependency (connect.source to
 * connect.target). The caller serializes + writes that single list once with a
 * single expected_hash. It re-runs the same per-endpoint guards the standalone
 * connect/disconnect helpers enforce (global node, self-dependency, unknown
 * phase, duplicate, missing) so the validation contract is unchanged; only the
 * round-trip count drops from two to one.
 */
export function reconnectPhaseRefs(
  detail: SkillDetail | undefined,
  disconnect: { source: string; target: string },
  connect: { source: string; target: string },
): ReconnectPhaseRefsResult {
  if (!disconnect.source || !disconnect.target || !connect.source || !connect.target) {
    return { ok: false, reason: 'invalid-endpoint', message: 'Edge endpoints must be phase nodes to reconnect.' }
  }
  if (connect.source === connect.target) {
    return { ok: false, reason: 'self-dependency', message: 'A phase cannot depend on itself.' }
  }
  if (disconnect.source === connect.source && disconnect.target === connect.target) {
    return { ok: false, reason: 'no-op', message: 'Edge was reconnected to the same endpoints.' }
  }

  const disconnected = disconnectPhaseRefs(detail, disconnect.source, disconnect.target)
  if (!disconnected.ok) {
    return disconnected
  }
  const connected = connectPhaseRefs(skillDetailFromPhaseRefs(disconnected.phases), connect.source, connect.target)
  if (!connected.ok) {
    return connected
  }
  return { ok: true, phases: connected.phases }
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

export function phaseDirectoryPath(phaseId: string): string {
  return `phases/${phaseId}`
}

// Node type is determined by the phase FILE KIND (LOGIC.md / SKILL.md /
// SUBGRAPH.md), never a `mode:` frontmatter field. The scaffolds below stay
// FROZEN-clean per engine skill-syntax §2.3 (LOGIC), §2.5 (agent SKILL),
// §2.4/§2.1 (SUBGRAPH) so the engine compiler accepts them with no
// unknown-field FATAL. Deprecated fields (`mode`, `system_prompt`,
// `exit_contract`, `python_callable`, legacy registry child-reference fields)
// must never be emitted.
export function defaultPhaseMarkdown(
  phaseId: string,
  kind: NewPhaseKind,
  subgraphPath?: string,
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
    'actions: []',
    '---',
    '',
  ].join('\n')
}

function agentPhaseMarkdown(phaseId: string): string {
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
    '---',
    '<role></role>',
    '<goal></goal>',
    '',
  ].join('\n')
}

function subgraphPhaseMarkdown(phaseId: string, subgraphPath?: string): string {
  return [
    '---',
    `name: ${phaseId}`,
    `path: ${subgraphPath ? subgraphPath : '""'}`,
    'io:',
    '  inputs:',
    '    type: object',
    '    properties: {}',
    '  outputs:',
    '    type: object',
    '    properties: {}',
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
