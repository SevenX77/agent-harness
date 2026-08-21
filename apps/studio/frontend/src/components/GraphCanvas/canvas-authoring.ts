import type { GraphPhaseMode, SerializableGraphPhaseRef, SkillDetail } from '@/api/types'
import { INPUT_ID, OUTPUT_ID } from '@/components/nodes'
import { parsePhaseFrontmatter } from '../studio/panels/phase-frontmatter'
import { defaultSubgraphChildDir } from '../studio/subgraph-scaffold'
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

/**
 * Why a graph edit was refused — the fact, not the sentence.
 *
 * These validators know which rule an edit broke; they do not know which
 * language the person at the canvas reads. So each one names its problem and
 * carries the params a message needs, and `graphEditProblemMessage` renders it
 * through the `canvas` namespace. Same split the backend/frontend error
 * contract uses (`04_platform/i18n.md` §3): produce a code plus structured
 * params, translate at the surface that knows the reader.
 *
 * The codes are finer-grained than the old `reason` field they replace: one
 * `invalid-endpoint` used to cover five different sentences, so `reason` could
 * never have driven the lookup on its own.
 */
export type GraphEditProblem =
  | { code: 'connect_endpoints_must_be_phases' }
  | { code: 'self_dependency' }
  | { code: 'input_target_must_be_phase' }
  | { code: 'dependency_exists' }
  | { code: 'output_source_must_be_phase' }
  | { code: 'output_marker_exists' }
  | { code: 'connect_boundary_direction' }
  | { code: 'disconnect_endpoints_must_be_phases' }
  | { code: 'input_source_must_be_phase' }
  | { code: 'input_dependency_missing' }
  | { code: 'output_disconnect_source_must_be_phase' }
  | { code: 'output_marker_missing' }
  | { code: 'disconnect_boundary_direction' }
  | { code: 'phase_dependency_missing' }
  | { code: 'phase_id_required' }
  | { code: 'phase_not_found' }
  | { code: 'select_phase_to_rename' }
  | { code: 'name_unchanged' }
  | { code: 'phase_not_in_graph' }
  | { code: 'reconnect_endpoints_must_be_phases' }
  | { code: 'reconnect_no_op' }
  | { code: 'name_required' }
  | { code: 'name_shape_invalid' }
  | { code: 'name_taken'; phaseId: string }

/**
 * A refused graph edit travelling as an exception.
 *
 * The canvas hands its edits to async handlers and reports failure by toasting
 * the rejected promise's `Error.message`. A plain `Error` can only carry a
 * finished sentence, which is what forced these validators to write English in
 * the first place. Carrying the problem instead keeps the fact intact all the
 * way to the toast, where `graphEditErrorMessage` renders it in the reader's
 * language. `message` holds the code so an unhandled rejection in the console
 * still says which rule fired.
 */
export class GraphEditError extends Error {
  readonly problem: GraphEditProblem

  constructor(problem: GraphEditProblem) {
    super(problem.code)
    this.name = 'GraphEditError'
    this.problem = problem
  }
}

export type ConnectPhaseRefsResult =
  | { ok: true; phases: SerializableGraphPhaseRef[] }
  | { ok: false; problem: GraphEditProblem }

export type RemovePhaseRefsResult =
  | { ok: true; phases: SerializableGraphPhaseRef[] }
  | { ok: false; problem: GraphEditProblem }

export type RenamePhaseRefsResult =
  | { ok: true; phases: SerializableGraphPhaseRef[] }
  | { ok: false; problem: GraphEditProblem }

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

/**
 * The three problems a proposed phase name can have.
 *
 * Carved out of `GraphEditProblem` rather than declared alongside it: the name
 * dialog rejects a name for exactly these reasons, and renaming an existing
 * phase rejects it for the same two shape rules. One definition of "this name
 * is taken" keeps the dialog and the rename path from drifting apart.
 */
export type PhaseNameProblem = Extract<
  GraphEditProblem,
  { code: 'name_required' | 'name_shape_invalid' | 'name_taken' }
>

export function phaseNameProblem(
  phaseId: string,
  detail: SkillDetail | undefined,
  reservedPhaseIds: Iterable<string> = [],
): PhaseNameProblem | null {
  const trimmed = phaseId.trim()
  if (!trimmed) {
    return { code: 'name_required' }
  }
  if (!isSafePhaseId(trimmed)) {
    return { code: 'name_shape_invalid' }
  }
  const existingIds = new Set([
    ...phaseRefsFromSkillDetail(detail).map((phase) => phase.id),
    ...phaseDirectoryIdsFromSkillDetail(detail),
    ...reservedPhaseIds,
  ])
  if (existingIds.has(trimmed)) {
    return { code: 'name_taken', phaseId: trimmed }
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
  const problem = requestedPhaseId ? phaseNameProblem(phaseId, detail, reservedPhaseIds) : null
  if (problem) {
    throw new GraphEditError(problem)
  }
  const filePath = phaseFilePath(phaseId, kind)
  const phaseRef: SerializableGraphPhaseRef = {
    id: phaseId,
    src: phaseDirectoryPath(phaseId),
    depends_on: [],
    mode: kind,
  }
  // A new subgraph phase defaults its `path:` to the skill-root-relative
  // `subgraph/<phaseId>` landing (graph-authoring F4 / engine FORMAT-GROUND-TRUTH
  // §4). The matching child skill folder is scaffolded by the Workspace create
  // handler so the reference resolves immediately.
  const subgraphPath = kind === 'subgraph' ? defaultSubgraphChildDir(phaseId) : undefined
  return {
    phaseId,
    filePath,
    fileContent: defaultPhaseMarkdown(phaseId, kind, subgraphPath),
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
    return { ok: false, problem: { code: 'connect_endpoints_must_be_phases' } }
  }
  if (sourceId === targetId) {
    return { ok: false, problem: { code: 'self_dependency' } }
  }

  const phases = phaseRefsFromSkillDetail(detail)
  if (sourceId === INPUT_ID) {
    const target = phases.find((phase) => phase.id === targetId)
    if (!target) {
      return { ok: false, problem: { code: 'input_target_must_be_phase' } }
    }
    if (target.depends_on.includes('input')) {
      return { ok: false, problem: { code: 'dependency_exists' } }
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
      return { ok: false, problem: { code: 'output_source_must_be_phase' } }
    }
    if (source.output === true) {
      return { ok: false, problem: { code: 'output_marker_exists' } }
    }
    return {
      ok: true,
      phases: phases.map((phase) => (
        phase.id === source.id ? { ...phase, output: true } : phase
      )),
    }
  }
  if (sourceId === OUTPUT_ID || targetId === INPUT_ID) {
    return { ok: false, problem: { code: 'connect_boundary_direction' } }
  }

  const source = phases.find((phase) => phase.id === sourceId)
  const target = phases.find((phase) => phase.id === targetId)
  if (!source || !target) {
    return { ok: false, problem: { code: 'connect_endpoints_must_be_phases' } }
  }
  if (target.depends_on.includes(source.id)) {
    return { ok: false, problem: { code: 'dependency_exists' } }
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
    return { ok: false, problem: { code: 'disconnect_endpoints_must_be_phases' } }
  }

  const phases = phaseRefsFromSkillDetail(detail)
  if (sourceId === INPUT_ID) {
    const target = phases.find((phase) => phase.id === targetId)
    if (!target) {
      return { ok: false, problem: { code: 'input_source_must_be_phase' } }
    }
    if (!target.depends_on.includes('input')) {
      return { ok: false, problem: { code: 'input_dependency_missing' } }
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
      return { ok: false, problem: { code: 'output_disconnect_source_must_be_phase' } }
    }
    if (source.output !== true) {
      return { ok: false, problem: { code: 'output_marker_missing' } }
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
    return { ok: false, problem: { code: 'disconnect_boundary_direction' } }
  }

  const source = phases.find((phase) => phase.id === sourceId)
  const target = phases.find((phase) => phase.id === targetId)
  if (!source || !target) {
    return { ok: false, problem: { code: 'disconnect_endpoints_must_be_phases' } }
  }
  if (!target.depends_on.includes(source.id)) {
    return { ok: false, problem: { code: 'phase_dependency_missing' } }
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
    return { ok: false, problem: { code: 'phase_id_required' } }
  }

  const phases = phaseRefsFromSkillDetail(detail)
  if (!phases.some((phase) => phase.id === phaseId)) {
    return { ok: false, problem: { code: 'phase_not_found' } }
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
    return { ok: false, problem: { code: 'select_phase_to_rename' } }
  }
  const nextId = nextPhaseId.trim()
  if (!isSafePhaseId(nextId)) {
    return { ok: false, problem: { code: 'name_shape_invalid' } }
  }
  if (nextId === phaseId) {
    return { ok: false, problem: { code: 'name_unchanged' } }
  }

  const phases = phaseRefsFromSkillDetail(detail)
  if (!phases.some((phase) => phase.id === phaseId)) {
    return { ok: false, problem: { code: 'phase_not_in_graph' } }
  }
  if (phases.some((phase) => phase.id === nextId)) {
    return { ok: false, problem: { code: 'name_taken', phaseId: nextId } }
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
  | { ok: false; problem: GraphEditProblem }

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
    return { ok: false, problem: { code: 'reconnect_endpoints_must_be_phases' } }
  }
  if (newSource === newTarget) {
    return { ok: false, problem: { code: 'self_dependency' } }
  }
  if (oldSource === newSource && oldTarget === newTarget) {
    return { ok: false, problem: { code: 'reconnect_no_op' } }
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
  | { ok: false; problem: GraphEditProblem }

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
    return { ok: false, problem: { code: 'reconnect_endpoints_must_be_phases' } }
  }
  if (connect.source === connect.target) {
    return { ok: false, problem: { code: 'self_dependency' } }
  }
  if (disconnect.source === connect.source && disconnect.target === connect.target) {
    return { ok: false, problem: { code: 'reconnect_no_op' } }
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
    // LOGIC requires at least one <action> tag (engine F-v3-logic-actions-empty), so
    // scaffold an empty one for the user to fill — the same idiom as the agent scaffold's
    // empty <role>/<goal>. Discoverable required tag, not a hidden must-add.
    '<action></action>',
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
