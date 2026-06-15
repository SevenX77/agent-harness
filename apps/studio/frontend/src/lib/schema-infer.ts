import yaml from 'js-yaml'
import type { JsonObject, JsonValue } from '../api/types'

export type InferredSchema = JsonObject

function inferType(value: JsonValue): InferredSchema {
  if (value === null) {
    return { type: 'null' }
  }

  if (Array.isArray(value)) {
    return {
      type: 'array',
      items: value.length > 0 ? inferType(value[0]) : {},
    }
  }

  if (typeof value === 'object') {
    const properties: JsonObject = {}
    const required: JsonValue[] = []
    Object.entries(value).forEach(([key, nested]) => {
      properties[key] = inferType(nested)
      required.push(key)
    })
    return {
      type: 'object',
      properties,
      required,
    }
  }

  return { type: typeof value }
}

export function inferJsonSchema(value: JsonValue): InferredSchema {
  return inferType(value)
}

export function inferJsonSchemaFromText(text: string): InferredSchema {
  return inferJsonSchema(JSON.parse(text) as JsonValue)
}

const FRONTMATTER_RE = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/

/**
 * F2 (i/o panel): persist an inferred/edited input schema into the skill's
 * authoritative input contract — the `io.inputs` block in GRAPH.md frontmatter
 * (what the engine validates against). Only `io.inputs` is replaced; `io.outputs`
 * and every other frontmatter key plus the GRAPH.md body (phase DAG) are
 * preserved. Pure + exported so the writeback is unit-testable without driving
 * the live panel. Throws if GRAPH.md has no frontmatter (caller surfaces it).
 */
export function applyInputSchemaToGraph(graphMd: string, inputSchema: JsonObject): string {
  const match = graphMd.match(FRONTMATTER_RE)
  if (!match) {
    throw new Error('GRAPH.md has no frontmatter to write the schema into')
  }
  const [, frontmatter, body] = match
  const data = (yaml.load(frontmatter) ?? {}) as Record<string, unknown>
  const io = (data.io && typeof data.io === 'object' ? data.io : {}) as Record<string, unknown>
  io.inputs = inputSchema
  data.io = io
  const nextFrontmatter = yaml.dump(data, { lineWidth: -1, noRefs: true })
  return `---\n${nextFrontmatter}---\n${body}`
}

/**
 * F3 (i/o panel): persist the destination of a declared output field's artifact
 * onto the `io.outputs.<field>` schema object in GRAPH.md frontmatter. The engine
 * honours `io.outputs.<field>.path` by writing the artifact to
 * `runs/<id>/artifacts/<path>`; a bare filename means "default under .workspace
 * artifacts" (the engine resolves the default, so we store the path verbatim).
 * Only the named field's `target`/`path` keys change — `io.inputs`, the other
 * output fields, every other frontmatter key, and the GRAPH.md body (phase DAG)
 * are preserved. An empty/whitespace path CLEARS the artifact target so the user
 * can unset it. Pure + exported so the writeback is unit-testable without driving
 * the live panel. Throws if GRAPH.md has no frontmatter, no `io.outputs.properties`,
 * or no such field (caller surfaces it).
 */
export function applyOutputArtifactPathToGraph(graphMd: string, fieldName: string, path: string): string {
  const match = graphMd.match(FRONTMATTER_RE)
  if (!match) {
    throw new Error('GRAPH.md has no frontmatter to write the output path into')
  }
  const [, frontmatter, body] = match
  const data = (yaml.load(frontmatter) ?? {}) as Record<string, unknown>
  const io = data.io && typeof data.io === 'object' ? (data.io as Record<string, unknown>) : null
  const outputs = io && io.outputs && typeof io.outputs === 'object' ? (io.outputs as Record<string, unknown>) : null
  const properties =
    outputs && outputs.properties && typeof outputs.properties === 'object'
      ? (outputs.properties as Record<string, unknown>)
      : null
  if (!properties) {
    throw new Error('GRAPH.md has no io.outputs.properties to write the output path into')
  }
  const field = properties[fieldName]
  if (!field || typeof field !== 'object') {
    throw new Error(`io.outputs has no output field "${fieldName}" to set an artifact path on`)
  }
  const schema = field as Record<string, unknown>
  const trimmed = path.trim()
  if (trimmed === '') {
    delete schema.target
    delete schema.path
  } else {
    schema.target = 'artifact'
    schema.path = trimmed
  }
  const nextFrontmatter = yaml.dump(data, { lineWidth: -1, noRefs: true })
  return `---\n${nextFrontmatter}---\n${body}`
}

// ---------------------------------------------------------------------------
// Field-level io schema editing (i/o panel)
//
// GRAPH.md `io.inputs`/`io.outputs` are JSON Schema objects (Draft 2020-12):
// top-level `type: object`, a `properties` map keyed by field name, and a
// `required` array referencing those property names. The functions below let
// the i/o panel edit those declared FIELDS one at a time — add / rename /
// remove / change type — writing back the same authoritative GRAPH.md
// frontmatter the engine validates. Each is pure + exported so the writeback is
// unit-testable without driving the live panel: only the targeted io side and
// the named field change; the other io side, every other frontmatter key, and
// the GRAPH.md body (phase DAG) are preserved verbatim.
// ---------------------------------------------------------------------------

/** Which io side a field-level edit targets. */
export type IoSide = 'inputs' | 'outputs'

/** JSON-schema primitive types offered by the field editor's type picker. */
export const IO_FIELD_TYPES = ['string', 'number', 'integer', 'boolean', 'object', 'array'] as const

export type IoFieldType = (typeof IO_FIELD_TYPES)[number]

/** A single declared io field, surfaced to the panel as a flat row. */
export interface IoField {
  name: string
  type: string
}

function frontmatterIoProperties(
  data: Record<string, unknown>,
  side: IoSide,
): { io: Record<string, unknown>; sideSchema: Record<string, unknown>; properties: Record<string, unknown> } {
  const io = (data.io && typeof data.io === 'object' ? data.io : {}) as Record<string, unknown>
  const sideSchema = (io[side] && typeof io[side] === 'object' ? io[side] : {}) as Record<string, unknown>
  // `io.<side>` is a JSON Schema object — keep it an object schema with a
  // properties map even if the source omitted them, so edits land in a valid
  // shape the engine accepts.
  if (typeof sideSchema.type !== 'string') {
    sideSchema.type = 'object'
  }
  const properties = (
    sideSchema.properties && typeof sideSchema.properties === 'object' ? sideSchema.properties : {}
  ) as Record<string, unknown>
  sideSchema.properties = properties
  io[side] = sideSchema
  data.io = io
  return { io, sideSchema, properties }
}

function loadGraphFrontmatter(graphMd: string): { data: Record<string, unknown>; body: string } {
  const match = graphMd.match(FRONTMATTER_RE)
  if (!match) {
    throw new Error('GRAPH.md has no frontmatter to edit io fields in')
  }
  const [, frontmatter, body] = match
  const data = (yaml.load(frontmatter) ?? {}) as Record<string, unknown>
  return { data, body }
}

function dumpGraph(data: Record<string, unknown>, body: string): string {
  const nextFrontmatter = yaml.dump(data, { lineWidth: -1, noRefs: true })
  return `---\n${nextFrontmatter}---\n${body}`
}

/** List the declared fields (name + json-schema type) on one io side of GRAPH.md. */
export function listIoFields(graphMd: string, side: IoSide): IoField[] {
  const match = graphMd.match(FRONTMATTER_RE)
  if (!match) {
    return []
  }
  const data = (yaml.load(match[1]) ?? {}) as Record<string, unknown>
  const io = data.io && typeof data.io === 'object' ? (data.io as Record<string, unknown>) : null
  const sideSchema = io && io[side] && typeof io[side] === 'object' ? (io[side] as Record<string, unknown>) : null
  const properties =
    sideSchema && sideSchema.properties && typeof sideSchema.properties === 'object'
      ? (sideSchema.properties as Record<string, unknown>)
      : null
  if (!properties) {
    return []
  }
  return Object.entries(properties).map(([name, schema]) => {
    const type =
      schema && typeof schema === 'object' && typeof (schema as { type?: unknown }).type === 'string'
        ? (schema as { type: string }).type
        : ''
    return { name, type }
  })
}

/** Add a new field of the given type to one io side. Throws if the name is blank or already declared. */
export function addIoField(graphMd: string, side: IoSide, name: string, type: IoFieldType): string {
  const fieldName = name.trim()
  if (fieldName === '') {
    throw new Error('io field name cannot be empty')
  }
  const { data, body } = loadGraphFrontmatter(graphMd)
  const { properties } = frontmatterIoProperties(data, side)
  if (fieldName in properties) {
    throw new Error(`io.${side} already declares a field named "${fieldName}"`)
  }
  properties[fieldName] = { type }
  return dumpGraph(data, body)
}

/** Remove a declared field from one io side, also dropping it from `required`. Throws if absent. */
export function removeIoField(graphMd: string, side: IoSide, name: string): string {
  const { data, body } = loadGraphFrontmatter(graphMd)
  const { sideSchema, properties } = frontmatterIoProperties(data, side)
  if (!(name in properties)) {
    throw new Error(`io.${side} has no field named "${name}" to remove`)
  }
  delete properties[name]
  if (Array.isArray(sideSchema.required)) {
    sideSchema.required = (sideSchema.required as unknown[]).filter((entry) => entry !== name)
  }
  return dumpGraph(data, body)
}

/** Rename a declared field on one io side, keeping its schema + position and updating `required`. */
export function renameIoField(graphMd: string, side: IoSide, from: string, to: string): string {
  const nextName = to.trim()
  if (nextName === '') {
    throw new Error('io field name cannot be empty')
  }
  const { data, body } = loadGraphFrontmatter(graphMd)
  const { sideSchema, properties } = frontmatterIoProperties(data, side)
  if (!(from in properties)) {
    throw new Error(`io.${side} has no field named "${from}" to rename`)
  }
  if (nextName === from) {
    return dumpGraph(data, body)
  }
  if (nextName in properties) {
    throw new Error(`io.${side} already declares a field named "${nextName}"`)
  }
  // Rebuild the properties map to preserve key ordering with the new name.
  const renamed: Record<string, unknown> = {}
  Object.entries(properties).forEach(([key, schema]) => {
    renamed[key === from ? nextName : key] = schema
  })
  sideSchema.properties = renamed
  if (Array.isArray(sideSchema.required)) {
    sideSchema.required = (sideSchema.required as unknown[]).map((entry) => (entry === from ? nextName : entry))
  }
  return dumpGraph(data, body)
}

/** Change a declared field's json-schema `type` on one io side, preserving its other schema keys. */
export function setIoFieldType(graphMd: string, side: IoSide, name: string, type: IoFieldType): string {
  const { data, body } = loadGraphFrontmatter(graphMd)
  const { properties } = frontmatterIoProperties(data, side)
  const field = properties[name]
  if (!field || typeof field !== 'object') {
    throw new Error(`io.${side} has no field named "${name}" to retype`)
  }
  ;(field as Record<string, unknown>).type = type
  return dumpGraph(data, body)
}
