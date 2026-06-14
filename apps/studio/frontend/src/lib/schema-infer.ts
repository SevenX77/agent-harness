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
