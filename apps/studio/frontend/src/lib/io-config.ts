import yaml from 'js-yaml'

import type { SkillDetail } from '@/api/types'

import { staticEdgeInference } from './edge-static-inference'
import { parseFrontmatter, phaseNodeFileContent, rootGraphFrontmatter, schemaObject } from './io-declarations'

/**
 * Pure logic for the blackboard-first I/O config dialogs (input region
 * F3/F7, PM 2026-07-02 r3).
 *
 * The blackboard is the primary data source for a node's inputs; imported
 * files only ADD fields on top. Accordingly the input config is a checkbox
 * tree — blackboard context first (checked = the node's io.inputs slice),
 * then per-file field trees (checked = `source:'file'` additions). The
 * output config is the symmetric artifacts manifest on GRAPH.md io
 * (files × blackboard-field checks; fixed on-disk format is engine-owned).
 *
 * Blackboard derivation is shared with the edge-dot static inference
 * (trace-observability F4) so the dot and the dialog can never disagree.
 */

export interface BlackboardCheckRow {
  name: string
  type: string | null
  /** Producer: 'input' (root io.inputs) or a phase id. */
  from: string
  /** true = currently declared in the node's io.inputs (consumed). */
  checked: boolean
}

export function blackboardAtNode(
  skillDetail: SkillDetail | undefined,
  nodeId: string,
): BlackboardCheckRow[] {
  const inference = staticEdgeInference(skillDetail, '', nodeId)
  if (!inference) {
    return []
  }
  return inference.fields
    .filter((field) => !field.via_file)
    .map((field) => ({
      name: field.name,
      type: field.type,
      from: field.from,
      checked: field.consumed_by_target,
    }))
}

/**
 * r4 field reconciliation (PM 2026-07-02): cross-check a node's declared io
 * against the fields ACTUALLY available.
 *  - matched:   declared in md io AND present in the available set
 *  - available: present but not declared
 *  - missing:   declared (required) but NOT available — a broken contract the
 *               engine would fail at runtime ([F-v3-runtime-state-mapping-failed]);
 *               surfaced at config time, at the TOP, muted + error.
 */
export type FieldMatchState = 'matched' | 'available' | 'missing'

export interface ReconciledFieldRow extends BlackboardCheckRow {
  state: FieldMatchState
  /** Populated for `missing` rows: why the field is unsatisfied. */
  reason?: string
}

function declaredIoProps(
  frontmatter: Record<string, unknown> | undefined,
  side: 'inputs' | 'outputs',
): Record<string, Record<string, unknown>> {
  const io = schemaObject(frontmatter?.io) ?? {}
  const props = schemaObject(schemaObject(io[side])?.properties) ?? {}
  const out: Record<string, Record<string, unknown>> = {}
  for (const [name, raw] of Object.entries(props)) {
    const schema = schemaObject(raw)
    if (schema) {
      out[name] = schema
    }
  }
  return out
}

function typeOfSchema(schema: Record<string, unknown>): string | null {
  return typeof schema.type === 'string' ? schema.type : null
}

/**
 * Input reconciliation for a node: blackboard fields tagged matched/available,
 * plus (at the top) any io.inputs field the upstream blackboard doesn't supply.
 * `source:'file'` inputs are injected from files, not the blackboard, so they
 * are never "missing". Empty for nodes with no blackboard (Input pseudo-node).
 */
export function reconcileInputFields(
  skillDetail: SkillDetail | undefined,
  nodeId: string,
): ReconciledFieldRow[] {
  // Input pseudo-node / GRAPH.md (no selected phase): no upstream blackboard.
  // A declared graph input with no `source:'file'` backing is unsourced — it
  // can only be filled by the run payload — so flag it missing so the author
  // sees the unwired entry field (PM 2026-07-02 r4b).
  if (!nodeId) {
    const declared = declaredIoProps(rootGraphFrontmatter(skillDetail), 'inputs')
    return Object.entries(declared)
      .filter(([, schema]) => schema.source !== 'file')
      .map(([name, schema]) => ({
        name,
        type: typeOfSchema(schema),
        from: 'io.inputs',
        checked: false,
        state: 'missing' as const,
        reason: 'declared graph input · no source supplied',
      }))
  }
  const blackboard = blackboardAtNode(skillDetail, nodeId)
  if (blackboard.length === 0) {
    return []
  }
  const bbNames = new Set(blackboard.map((row) => row.name))
  const declared = declaredIoProps(parseFrontmatter(phaseNodeFileContent(skillDetail, nodeId)), 'inputs')

  const missing: ReconciledFieldRow[] = []
  for (const [name, schema] of Object.entries(declared)) {
    if (schema.source === 'file' || bbNames.has(name)) {
      continue
    }
    missing.push({
      name,
      type: typeOfSchema(schema),
      from: 'io.inputs',
      checked: false,
      state: 'missing',
      reason: 'required by io.inputs · not supplied by upstream',
    })
  }
  const rest: ReconciledFieldRow[] = blackboard.map((row) => ({
    ...row,
    state: row.checked ? 'matched' : 'available',
  }))
  return [...missing, ...rest]
}

/**
 * Output reconciliation at the graph boundary: the field universe (root inputs
 * ∪ every phase's outputs) tagged matched (a declared GRAPH.md io.outputs
 * member) / available, plus (at the top) any io.outputs field NO phase
 * produces.
 */
export function reconcileOutputFields(
  skillDetail: SkillDetail | undefined,
): ReconciledFieldRow[] {
  const universe = blackboardAtOutput(skillDetail)
  const universeNames = new Set(universe.map((row) => row.name))
  const declared = declaredIoProps(rootGraphFrontmatter(skillDetail), 'outputs')

  const missing: ReconciledFieldRow[] = []
  for (const [name, schema] of Object.entries(declared)) {
    if (universeNames.has(name)) {
      continue
    }
    missing.push({
      name,
      type: typeOfSchema(schema),
      from: 'io.outputs',
      checked: false,
      state: 'missing',
      reason: 'required by io.outputs · no phase produces it',
    })
  }
  const declaredNames = new Set(Object.keys(declared))
  const rows: ReconciledFieldRow[] = universe.map((row) => ({
    ...row,
    state: declaredNames.has(row.name) ? 'matched' : 'available',
  }))
  const matched = rows.filter((row) => row.state === 'matched')
  const available = rows.filter((row) => row.state === 'available')
  return [...missing, ...matched, ...available]
}

export interface FileFieldDecl {
  field: string
  type: string | null
  /** Single-file injection: workspace-relative path. */
  path?: string
  /** Batch injection: workspace-relative dir + `{n}` pattern (+ number list). */
  dir?: string
  pattern?: string
  numbers?: number[]
}

const FRONTMATTER_RE = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/

function mutateFrontmatter(
  content: string,
  mutate: (data: Record<string, unknown>) => void,
): string {
  const match = content.match(FRONTMATTER_RE)
  if (!match) {
    throw new Error('document has no frontmatter to write io config into')
  }
  const [, frontmatter, body] = match
  const data = (yaml.load(frontmatter) ?? {}) as Record<string, unknown>
  mutate(data)
  const nextFrontmatter = yaml.dump(data, { lineWidth: -1, noRefs: true })
  return `---\n${nextFrontmatter}---\n${body}`
}

function ioOf(data: Record<string, unknown>): Record<string, unknown> {
  const io = (data.io && typeof data.io === 'object' ? data.io : {}) as Record<string, unknown>
  data.io = io
  return io
}

export interface IoInputChecks {
  blackboard: Array<{ name: string; type: string | null; checked: boolean }>
  files: FileFieldDecl[]
}

/**
 * Rebuild a node file's `io.inputs` from the dialog state: checked
 * blackboard fields become the consumed slice; file declarations append
 * their `source:'file'` fields (single path or batch dir+pattern). Non-file
 * properties NOT present in the blackboard list (e.g. runtime payload
 * fields on GRAPH.md) are preserved untouched.
 */
export function applyIoInputChecks(content: string, checks: IoInputChecks): string {
  return mutateFrontmatter(content, (data) => {
    const io = ioOf(data)
    const previous = schemaObject(io.inputs) ?? {}
    const previousProperties = schemaObject(previous.properties) ?? {}

    const properties: Record<string, unknown> = {}
    const blackboardNames = new Set(checks.blackboard.map((row) => row.name))
    for (const [name, schema] of Object.entries(previousProperties)) {
      const declared = schemaObject(schema) ?? {}
      if (declared.source === 'file' || blackboardNames.has(name)) {
        continue
      }
      properties[name] = schema
    }
    for (const row of checks.blackboard) {
      if (!row.checked) {
        continue
      }
      const declared = schemaObject(previousProperties[row.name]) ?? {}
      properties[row.name] = {
        ...declared,
        ...(row.type ? { type: row.type } : {}),
      }
    }
    for (const file of checks.files) {
      const entry: Record<string, unknown> = {
        ...(file.type ? { type: file.type } : {}),
        source: 'file',
      }
      if (file.dir && file.pattern) {
        entry.dir = file.dir
        entry.pattern = file.pattern
        if (file.numbers && file.numbers.length > 0) {
          entry.numbers = file.numbers
        }
      } else if (file.path) {
        entry.path = file.path
      }
      properties[file.field] = entry
    }

    io.inputs = {
      type: 'object',
      required: Object.keys(properties),
      properties,
    }
  })
}

export interface ArtifactRow {
  stem: string
  mode: 'single' | 'per-item'
  format?: 'json' | 'md'
  fields: string[]
}

/** Write the artifacts manifest onto GRAPH.md io (empty list removes it). */
export function applyGraphArtifacts(graphMd: string, artifacts: ArtifactRow[]): string {
  return mutateFrontmatter(graphMd, (data) => {
    const io = ioOf(data)
    if (artifacts.length === 0) {
      delete io.artifacts
      return
    }
    io.artifacts = artifacts.map((row) => ({
      stem: row.stem,
      mode: row.mode,
      ...(row.format && row.format !== 'json' ? { format: row.format } : {}),
      fields: row.fields,
    }))
  })
}

/** Read the declared artifacts manifest from GRAPH.md frontmatter. */
export function graphArtifactsOf(skillDetail: SkillDetail | undefined): ArtifactRow[] {
  const frontmatter = rootGraphFrontmatter(skillDetail)
  const io = schemaObject(frontmatter?.io) ?? {}
  const raw = io.artifacts
  if (!Array.isArray(raw)) {
    return []
  }
  const rows: ArtifactRow[] = []
  for (const item of raw) {
    const entry = schemaObject(item)
    if (!entry || typeof entry.stem !== 'string' || !Array.isArray(entry.fields)) {
      continue
    }
    rows.push({
      stem: entry.stem,
      mode: entry.mode === 'per-item' ? 'per-item' : 'single',
      format: entry.format === 'md' ? 'md' : 'json',
      fields: entry.fields.filter((f): f is string => typeof f === 'string'),
    })
  }
  return rows
}

/** File-sourced input declarations of a node (or GRAPH.md via nodeContent). */
export function fileFieldsOf(nodeContent: string | undefined): FileFieldDecl[] {
  const frontmatter = parseFrontmatter(nodeContent)
  const io = schemaObject(frontmatter?.io) ?? {}
  const inputs = schemaObject(io.inputs) ?? {}
  const properties = schemaObject(inputs.properties) ?? {}
  const rows: FileFieldDecl[] = []
  for (const [name, raw] of Object.entries(properties)) {
    const schema = schemaObject(raw)
    if (!schema || schema.source !== 'file') {
      continue
    }
    rows.push({
      field: name,
      type: typeof schema.type === 'string' ? schema.type : null,
      ...(typeof schema.path === 'string' ? { path: schema.path } : {}),
      ...(typeof schema.dir === 'string' ? { dir: schema.dir } : {}),
      ...(typeof schema.pattern === 'string' ? { pattern: schema.pattern } : {}),
      ...(Array.isArray(schema.numbers)
        ? { numbers: schema.numbers.filter((n): n is number => typeof n === 'number') }
        : {}),
    })
  }
  return rows
}

/**
 * Field universe at the Output pseudo-node: root io.inputs plus every phase's
 * declared outputs (topology order, later phases overwrite same names) — the
 * checkbox list every artifact file offers (identical under each file).
 */
export function blackboardAtOutput(skillDetail: SkillDetail | undefined): BlackboardCheckRow[] {
  const frontmatter = rootGraphFrontmatter(skillDetail)
  const io = schemaObject(frontmatter?.io) ?? {}
  const rows = new Map<string, BlackboardCheckRow>()
  const rootInputs = schemaObject(schemaObject(io.inputs)?.properties) ?? {}
  for (const [name, raw] of Object.entries(rootInputs)) {
    const schema = schemaObject(raw)
    rows.set(name, {
      name,
      type: schema && typeof schema.type === 'string' ? schema.type : null,
      from: 'input',
      checked: false,
    })
  }
  const topology = (skillDetail?.graph_topology ?? []) as unknown as Array<{ id: string }>
  for (const phase of topology) {
    const content = phaseNodeFileContent(skillDetail, phase.id)
    const phaseIo = schemaObject(parseFrontmatter(content)?.io) ?? {}
    const outputs = schemaObject(schemaObject(phaseIo.outputs)?.properties) ?? {}
    for (const [name, raw] of Object.entries(outputs)) {
      const schema = schemaObject(raw)
      rows.set(name, {
        name,
        type: schema && typeof schema.type === 'string' ? schema.type : null,
        from: phase.id,
        checked: false,
      })
    }
  }
  return [...rows.values()]
}
