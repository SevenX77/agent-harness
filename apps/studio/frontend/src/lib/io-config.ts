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
