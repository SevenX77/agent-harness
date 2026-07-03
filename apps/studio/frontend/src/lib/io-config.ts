import yaml from 'js-yaml'

import type { SkillDetail } from '@/api/types'

import { staticEdgeInference } from './edge-static-inference'
import {
  fieldPathRows,
  flattenFieldPaths,
  parseFrontmatter,
  phaseNodeFileContent,
  rootGraphFrontmatter,
  schemaObject,
  type JsonSchemaObject,
} from './io-declarations'

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
  /** Leaf segment for display, e.g. `aa_number`. */
  name: string
  /** Dotted full path identity, e.g. `chapter.aa_number`. */
  path: string
  /** Nesting depth (0 = top-level) for tree indentation. */
  depth: number
  type: string | null
  /** Producer: 'input' (root io.inputs) or a phase id. */
  from: string
  /** true = currently declared in the node's io.inputs at THIS path (consumed). */
  checked: boolean
  /** True when this object field has nested sub-fields to expand. */
  hasChildren: boolean
}

/** A field row's display type, falling back to `object` for a nested container. */
function rowType(schema: JsonSchemaObject, hasChildren: boolean): string | null {
  if (typeof schema.type === 'string') {
    return schema.type
  }
  return hasChildren ? 'object' : null
}

/**
 * The blackboard as an expandable field tree (flat rows carrying a dotted `path`
 * + `depth`): every top-level blackboard field plus its nested object sub-paths
 * (`chapter` → `chapter.aa_number`), pre-order so a parent precedes its children.
 * `checked` = the node's io.inputs declares THAT exact path (nested addressing,
 * PM 2026-07-03). Shares the edge-dot static inference so the dot and the config
 * tree can never disagree.
 */
export function blackboardAtNode(
  skillDetail: SkillDetail | undefined,
  nodeId: string,
): BlackboardCheckRow[] {
  const inference = staticEdgeInference(skillDetail, '', nodeId)
  if (!inference) {
    return []
  }
  const declaredPaths = new Set(
    flattenFieldPaths(declaredIoProps(parseFrontmatter(phaseNodeFileContent(skillDetail, nodeId)), 'inputs')),
  )
  const rows: BlackboardCheckRow[] = []
  for (const field of inference.fields) {
    if (field.via_file) {
      continue
    }
    for (const treeRow of fieldPathRows({ [field.name]: field.schema })) {
      rows.push({
        name: treeRow.name,
        path: treeRow.path,
        depth: treeRow.depth,
        type: rowType(treeRow.schema, treeRow.hasChildren),
        from: field.from,
        checked: declaredPaths.has(treeRow.path),
        hasChildren: treeRow.hasChildren,
      })
    }
  }
  return rows
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

/** `chapter.meta.title` → `[chapter, chapter.meta]` — every ancestor object path. */
function ancestorPrefixes(path: string): string[] {
  const parts = path.split('.')
  const out: string[] = []
  for (let i = 1; i < parts.length; i += 1) {
    out.push(parts.slice(0, i).join('.'))
  }
  return out
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
 * The declared io.inputs top-level field names of a node/GRAPH.md document —
 * the targets an imported file's fields auto-match against (input region F5,
 * PM 2026-07-02 r2「推断…是否匹配」; the import surfaces the match, PM 2026-07-03).
 */
export function declaredInputFieldNames(nodeContent: string | undefined): string[] {
  return Object.keys(declaredIoProps(parseFrontmatter(nodeContent), 'inputs'))
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
  // sees the unwired entry field (PM 2026-07-02 r4b). Nested addressing: the
  // topmost unsourced object path stands for its whole subtree.
  if (!nodeId) {
    const declared = declaredIoProps(rootGraphFrontmatter(skillDetail), 'inputs')
    return missingDeclaredRows(
      declared,
      () => false,
      'declared graph input · no source supplied',
    )
  }
  const blackboard = blackboardAtNode(skillDetail, nodeId)
  if (blackboard.length === 0) {
    return []
  }
  const suppliedPaths = new Set(blackboard.map((row) => row.path))
  const declared = declaredIoProps(parseFrontmatter(phaseNodeFileContent(skillDetail, nodeId)), 'inputs')

  const missing = missingDeclaredRows(
    declared,
    (path) => suppliedPaths.has(path),
    'required by io.inputs · not supplied by upstream',
  )
  const rest: ReconciledFieldRow[] = blackboard.map((row) => ({
    ...row,
    state: row.checked ? 'matched' : 'available',
  }))
  return [...missing, ...rest]
}

/**
 * Declared io.inputs paths (nested) not satisfied by `isSupplied`, as `missing`
 * rows — skipping `source:'file'` top-level fields (file-injected, never a
 * blackboard gap) and any path whose ancestor is already missing (the topmost
 * unmet object stands for its subtree, so the tree isn't spammed with children).
 */
function missingDeclaredRows(
  declared: Record<string, Record<string, unknown>>,
  isSupplied: (path: string) => boolean,
  reason: string,
): ReconciledFieldRow[] {
  const missing: ReconciledFieldRow[] = []
  const missingPaths = new Set<string>()
  for (const row of fieldPathRows(declared)) {
    const topSchema = schemaObject(declared[row.path.split('.')[0]]) ?? {}
    if (topSchema.source === 'file' || isSupplied(row.path)) {
      continue
    }
    if (ancestorPrefixes(row.path).some((ancestor) => missingPaths.has(ancestor))) {
      continue
    }
    missingPaths.add(row.path)
    missing.push({
      name: row.name,
      path: row.path,
      depth: row.depth,
      type: rowType(row.schema, row.hasChildren),
      from: 'io.inputs',
      checked: false,
      hasChildren: row.hasChildren,
      state: 'missing',
      reason,
    })
  }
  return missing
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
  const topLevelUniverse = new Set(universe.filter((row) => row.depth === 0).map((row) => row.name))
  const declared = declaredIoProps(rootGraphFrontmatter(skillDetail), 'outputs')

  const missing: ReconciledFieldRow[] = []
  for (const [name, schema] of Object.entries(declared)) {
    if (topLevelUniverse.has(name)) {
      continue
    }
    missing.push({
      name,
      path: name,
      depth: 0,
      type: typeOfSchema(schema),
      from: 'io.outputs',
      checked: false,
      hasChildren: false,
      state: 'missing',
      reason: 'required by io.outputs · no phase produces it',
    })
  }
  // A top-level field is `matched` when GRAPH.md io.outputs declares it (its
  // nested sub-rows inherit the match for display). Universe order is kept
  // (pre-order) so nested sub-fields stay under their parent — artifacts carry a
  // whole top-level field, so nested rows are shown for shape, not sub-selected.
  const declaredNames = new Set(Object.keys(declared))
  const rows: ReconciledFieldRow[] = universe.map((row) => ({
    ...row,
    state: declaredNames.has(row.path.split('.')[0]) ? 'matched' : 'available',
  }))
  return [...missing, ...rows]
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

export interface IoInputCheckRow {
  /** Dotted path (`chapter.aa_number`) — the addressable field identity. */
  path: string
  type: string | null
  checked: boolean
}

export interface IoInputChecks {
  blackboard: IoInputCheckRow[]
  files: FileFieldDecl[]
}

interface NestedBuild {
  properties: Record<string, unknown>
  required: string[]
}

/**
 * Project a set of checked dotted paths into a nested JSON-Schema `properties`
 * tree with per-level `required`. Checking `chapter.aa_number` declares
 * `chapter` as a required object whose `aa_number` is required — so the studio
 * config exactly reproduces the shape the engine's recursive required gate
 * enforces (nested addressing, PM 2026-07-03). Checking a bare object path with
 * no checked children declares it as an opaque required object.
 */
function nestedPropertiesFromPaths(rows: Array<{ path: string; type: string | null }>): NestedBuild {
  const groups = new Map<string, Array<{ path: string; type: string | null }>>()
  const order: string[] = []
  for (const row of rows) {
    const dot = row.path.indexOf('.')
    const head = dot === -1 ? row.path : row.path.slice(0, dot)
    const rest = dot === -1 ? '' : row.path.slice(dot + 1)
    if (!groups.has(head)) {
      groups.set(head, [])
      order.push(head)
    }
    groups.get(head)!.push({ path: rest, type: row.type })
  }
  const properties: Record<string, unknown> = {}
  for (const head of order) {
    const members = groups.get(head)!
    const childRows = members.filter((member) => member.path !== '')
    if (childRows.length > 0) {
      const nested = nestedPropertiesFromPaths(childRows)
      properties[head] = { type: 'object', required: nested.required, properties: nested.properties }
    } else {
      const leaf = members.find((member) => member.path === '')
      properties[head] = leaf?.type ? { type: leaf.type } : {}
    }
  }
  return { properties, required: order }
}

/**
 * Rebuild a node file's `io.inputs` from the dialog state: checked blackboard
 * paths become the consumed (nested) slice; file declarations append their
 * `source:'file'` fields (single path or batch dir+pattern). Non-file top-level
 * properties NOT touched by the blackboard checks (e.g. runtime payload fields
 * on GRAPH.md) are preserved untouched.
 */
export function applyIoInputChecks(content: string, checks: IoInputChecks): string {
  return mutateFrontmatter(content, (data) => {
    const io = ioOf(data)
    const previous = schemaObject(io.inputs) ?? {}
    const previousProperties = schemaObject(previous.properties) ?? {}

    // Top-level fields owned by the blackboard tree — preserve everything else.
    const blackboardTopNames = new Set(checks.blackboard.map((row) => row.path.split('.')[0]))
    const properties: Record<string, unknown> = {}
    for (const [name, schema] of Object.entries(previousProperties)) {
      const declared = schemaObject(schema) ?? {}
      if (declared.source === 'file' || blackboardTopNames.has(name)) {
        continue
      }
      properties[name] = schema
    }

    const built = nestedPropertiesFromPaths(
      checks.blackboard.filter((row) => row.checked).map((row) => ({ path: row.path, type: row.type })),
    )
    for (const [name, schema] of Object.entries(built.properties)) {
      properties[name] = schema
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
  // Merge root inputs + each phase's outputs by TOP-LEVEL name (topology order,
  // later phases overwrite same names), preserving each field's schema so nested
  // object outputs (segmentation_result → segmentation_result.bb_number) expand.
  const fieldSchemas = new Map<string, { schema: JsonSchemaObject; from: string }>()
  const rootInputs = schemaObject(schemaObject(io.inputs)?.properties) ?? {}
  for (const [name, raw] of Object.entries(rootInputs)) {
    fieldSchemas.set(name, { schema: schemaObject(raw) ?? {}, from: 'input' })
  }
  const topology = (skillDetail?.graph_topology ?? []) as unknown as Array<{ id: string }>
  for (const phase of topology) {
    const content = phaseNodeFileContent(skillDetail, phase.id)
    const phaseIo = schemaObject(parseFrontmatter(content)?.io) ?? {}
    const outputs = schemaObject(schemaObject(phaseIo.outputs)?.properties) ?? {}
    for (const [name, raw] of Object.entries(outputs)) {
      fieldSchemas.set(name, { schema: schemaObject(raw) ?? {}, from: phase.id })
    }
  }
  const rows: BlackboardCheckRow[] = []
  for (const [name, { schema, from }] of fieldSchemas) {
    for (const treeRow of fieldPathRows({ [name]: schema })) {
      rows.push({
        name: treeRow.name,
        path: treeRow.path,
        depth: treeRow.depth,
        type: rowType(treeRow.schema, treeRow.hasChildren),
        from,
        checked: false,
        hasChildren: treeRow.hasChildren,
      })
    }
  }
  return rows
}
