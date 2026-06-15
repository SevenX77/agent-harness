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
