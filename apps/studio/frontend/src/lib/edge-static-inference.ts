import type { RuntimeConfig, RuntimeImportEntry, RuntimeImportField, SkillDetail } from '@/api/types'
import {
  ioPropertiesOf,
  parseFrontmatter,
  phaseNodeFileContent,
  rootGraphFrontmatter,
  schemaObject,
} from './io-declarations'

/**
 * Static (pre-run) edge-dot blackboard inference — trace-observability F4 /
 * n5 atom #14 (PM 2026-07-02).
 *
 * Before any run exists, clicking an edge dot should still answer "which
 * fields SHOULD be on the blackboard when the graph reaches this dot". The
 * derivation mirrors the engine's compile-time dataflow rules, computed
 * entirely from the skill's DECLARATIONS:
 *
 *   fields at edge(source -> target) =
 *       root io.inputs
 *     ∪ io.outputs of every ancestor phase of `target`
 *     ∪ the target's runtime_config file inputs (lazily injected right
 *       before the target runs — exactly at this dot)
 *
 * A field name produced by multiple ancestors resolves to the NEAREST
 * ancestor (sequential overwrite: the later write wins on the blackboard).
 * Fields the target will slice off the blackboard (its io.inputs) are marked
 * `consumed_by_target` so the dot view can show the dispatch boundary.
 *
 * Field truth is read from the skill FILES' frontmatter (GRAPH.md root io +
 * per-phase node files) — the same authoritative source the i/o panel renders.
 * `graph_topology` supplies only ids + depends_on for traversal; its
 * `io_fields` projection is derived and degrades to empty on compile errors,
 * so it is deliberately not consumed here. Pure and frontend-only: engine
 * graph-exec E4 assigns canvas blackboard visualisation to the frontend.
 */

export interface StaticEdgeField {
  name: string
  type: string | null
  /** Producer: 'input' (root io.inputs), a phase id, or the file path for via_file fields. */
  from: string
  via_file: boolean
  consumed_by_target: boolean
  /**
   * The field's raw JSON subschema, so consumers (i/o config tree) can descend
   * into nested object `properties` for nested addressing (PM 2026-07-03). The
   * edge-dot view ignores it; it is purely additive.
   */
  schema: FieldSchema
}

export interface StaticEdgeInference {
  kind: 'static_inference'
  source: string
  target: string
  fields: StaticEdgeField[]
  [key: string]: unknown
}

const ROOT_DEP_IDS = new Set(['input', '__global_input__'])
const OUTPUT_IDS = new Set(['output', '__global_output__'])

type FieldSchema = Record<string, unknown>

interface TopologyPhase {
  id: string
  depends_on?: string[] | null
}

function fieldSchema(value: unknown): FieldSchema {
  return schemaObject(value) ?? {}
}

function fieldType(schema: FieldSchema): string | null {
  return typeof schema.type === 'string' ? schema.type : null
}

function runtimeBatchFieldName(entry: RuntimeImportEntry): string {
  const raw = entry.pattern ?? entry.stem ?? entry.name
  const withoutExt = raw.replace(/\.[^.]+$/, '')
  return withoutExt.split(/_?\{n\}/)[0].replace(/[._-]+$/, '') || withoutExt
}

function runtimeFieldSchema(field: RuntimeImportField): FieldSchema {
  return typeof field.type === 'string' ? { type: field.type } : {}
}

function runtimeImportFields(entries: RuntimeImportEntry[]): StaticEdgeField[] {
  const rows: StaticEdgeField[] = []
  for (const entry of entries) {
    if (entry.kind === 'dir') {
      rows.push(...runtimeImportFields(entry.entries ?? []))
      continue
    }
    if (entry.kind === 'batch') {
      const name = runtimeBatchFieldName(entry)
      rows.push({
        name,
        type: 'array',
        from: typeof entry.dir === 'string' ? entry.dir : 'runtime_config',
        via_file: true,
        consumed_by_target: false,
        schema: { type: 'array' },
      })
      continue
    }
    for (const field of entry.fields ?? []) {
      if (typeof field.name !== 'string' || !field.name) {
        continue
      }
      const schema = runtimeFieldSchema(field)
      rows.push({
        name: field.name,
        type: fieldType(schema),
        from: typeof entry.path === 'string' ? entry.path : 'runtime_config',
        via_file: true,
        consumed_by_target: false,
        schema,
      })
    }
  }
  return rows
}

interface PhaseDeclarations {
  inputs: Record<string, unknown>
  outputs: Record<string, unknown>
}

function phaseDeclarations(skillDetail: SkillDetail | undefined, phaseId: string): PhaseDeclarations {
  const frontmatter = parseFrontmatter(phaseNodeFileContent(skillDetail, phaseId))
  return {
    inputs: ioPropertiesOf(frontmatter, 'inputs'),
    outputs: ioPropertiesOf(frontmatter, 'outputs'),
  }
}

export function staticEdgeInference(
  skillDetail: SkillDetail | undefined,
  source: string,
  target: string,
  runtimeConfig?: RuntimeConfig | null,
): StaticEdgeInference | null {
  const topology = (skillDetail?.graph_topology ?? []) as unknown as TopologyPhase[]
  if (topology.length === 0) {
    return null
  }
  const byId = new Map(topology.map((phase) => [phase.id, phase]))
  const rootFrontmatter = rootGraphFrontmatter(skillDetail)

  // The terminal edge (phase -> Output pseudo-node): the blackboard is what the
  // source and its ancestors produced; the "consumer" is the root io.outputs.
  const isTerminalEdge = !byId.has(target) && OUTPUT_IDS.has(target) && byId.has(source)
  const anchor = isTerminalEdge ? source : target
  if (!byId.has(anchor)) {
    return null
  }

  // BFS upstream from the anchor: distance = hops, so the producer with the
  // SMALLEST distance is the nearest ancestor (its write is the last one
  // standing on the blackboard). For the terminal edge the anchor itself is a
  // producer too (distance 0).
  const distance = new Map<string, number>()
  let rootReachable = false
  if (isTerminalEdge) {
    distance.set(anchor, 0)
  }
  const queue: Array<{ id: string; hops: number }> = [{ id: anchor, hops: 0 }]
  const seen = new Set<string>([anchor])
  while (queue.length > 0) {
    const current = queue.shift()!
    const phase = byId.get(current.id)
    for (const dep of phase?.depends_on ?? []) {
      if (ROOT_DEP_IDS.has(dep)) {
        rootReachable = true
        continue
      }
      if (!byId.has(dep) || seen.has(dep)) {
        continue
      }
      seen.add(dep)
      distance.set(dep, current.hops + 1)
      queue.push({ id: dep, hops: current.hops + 1 })
    }
  }

  const fields = new Map<string, StaticEdgeField>()

  // Root inputs are conceptually the farthest writes — apply first so any
  // ancestor output with the same name overwrites them.
  if (rootReachable || distance.size === 0) {
    for (const [name, raw] of Object.entries(ioPropertiesOf(rootFrontmatter, 'inputs'))) {
      fields.set(name, {
        name,
        type: fieldType(fieldSchema(raw)),
        from: 'input',
        via_file: false,
        consumed_by_target: false,
        schema: fieldSchema(raw),
      })
    }
  }

  // Ancestor outputs, farthest first so nearer producers overwrite same-name fields.
  const producers = [...distance.entries()].sort((a, b) => b[1] - a[1])
  const declarations = new Map<string, PhaseDeclarations>()
  const declarationsOf = (phaseId: string): PhaseDeclarations => {
    let cached = declarations.get(phaseId)
    if (!cached) {
      cached = phaseDeclarations(skillDetail, phaseId)
      declarations.set(phaseId, cached)
    }
    return cached
  }
  for (const [phaseId] of producers) {
    for (const [name, raw] of Object.entries(declarationsOf(phaseId).outputs)) {
      fields.set(name, {
        name,
        type: fieldType(fieldSchema(raw)),
        from: phaseId,
        via_file: false,
        consumed_by_target: false,
        schema: fieldSchema(raw),
      })
    }
  }

  // The consumer boundary: a phase target slices its declared io.inputs off
  // the blackboard; the Output pseudo-node "consumes" the root io.outputs.
  const consumerInputs = isTerminalEdge
    ? ioPropertiesOf(rootFrontmatter, 'outputs')
    : declarationsOf(target).inputs

  // Runtime-config file imports inject at exactly this dot (lazy, right before
  // the target runs). Not applicable to the terminal edge.
  if (!isTerminalEdge) {
    const phaseRuntimeEntries = runtimeConfig?.inputs?.manifest?.phases?.[target] ?? []
    for (const field of runtimeImportFields(phaseRuntimeEntries)) {
      fields.set(field.name, field)
    }
  }

  const consumed = new Set(Object.keys(consumerInputs))
  for (const field of fields.values()) {
    field.consumed_by_target = consumed.has(field.name)
  }

  const sorted = [...fields.values()].sort((a, b) => {
    if (a.consumed_by_target !== b.consumed_by_target) {
      return a.consumed_by_target ? -1 : 1
    }
    return a.name.localeCompare(b.name)
  })

  return { kind: 'static_inference', source, target, fields: sorted }
}

export function isStaticEdgeInference(value: unknown): value is StaticEdgeInference {
  return (
    value != null
    && typeof value === 'object'
    && (value as { kind?: unknown }).kind === 'static_inference'
    && Array.isArray((value as { fields?: unknown }).fields)
  )
}
