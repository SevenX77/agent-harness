import type { GraphPhaseMode, SerializableGraphPhaseRef, SkillDetail } from '@/api/types'
import { INPUT_ID, OUTPUT_ID } from '@/components/nodes'

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
  if (detail?.manifest.schema_version !== '2.1') {
    return []
  }

  const topologyById = new Map((detail.graph_topology ?? []).map((phase) => [phase.id, phase]))
  return detail.manifest.phases.map((phase) => {
    const topology = topologyById.get(phase.id)
    const mode = normalizePhaseMode(topology?.mode) ?? modeFromSrc(topology?.src ?? phase.src)
    return {
      id: phase.id,
      src: topology?.src ?? phase.src,
      depends_on: [...(topology?.depends_on ?? phase.depends_on ?? [])],
      mode,
    }
  })
}

export function createPhaseDraft(detail: SkillDetail | undefined, kind: NewPhaseKind, skillId?: string): PhaseDraft {
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
    fileContent: defaultPhaseMarkdown(phaseId, kind, skillId),
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

export function defaultPhaseMarkdown(phaseId: string, kind: NewPhaseKind, skillId = 'placeholder.child_skill'): string {
  if (kind === 'skill') {
    return [
      '---',
      `name: ${phaseId}`,
      'mode: skill',
      'tools: []',
      '---',
      '',
      '<system_prompt>',
      `Describe what ${phaseId} should do.`,
      '</system_prompt>',
      '',
      '<exit_contract>',
      'Call finish_task when this phase is complete.',
      '</exit_contract>',
      '',
      `# ${phaseId}`,
      '',
    ].join('\n')
  }
  if (kind === 'subgraph') {
    return [
      '---',
      `name: ${phaseId}`,
      'mode: subgraph',
      `target_skill: ${skillId}`,
      '---',
      '',
      `# ${phaseId}`,
      '',
    ].join('\n')
  }
  return [
    '---',
    `name: ${phaseId}`,
    'mode: logic',
    '---',
    '',
    '<python_callable>',
    phaseId.replaceAll('-', '_'),
    '</python_callable>',
    '',
    `# ${phaseId}`,
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
