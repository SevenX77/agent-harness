import yaml from 'js-yaml'
import type { SkillDetail } from '@/api/types'

/**
 * Shared io-declaration readers. The AUTHORITATIVE io contract lives inline in
 * each md file's frontmatter (`GRAPH.md` root io, `phases/<id>/{SKILL,LOGIC,
 * SUBGRAPH}.md` per-phase io). Derived projections (`manifest.io`,
 * `graph_topology[].io_fields`) can lag or degrade to empty (e.g. while the
 * skill has compile errors), so anything that needs field truth parses the
 * files instead — same source the i/o panel renders.
 */

export type JsonSchemaObject = Record<string, unknown>
export type IoSide = 'inputs' | 'outputs'

const FRONTMATTER_RE = /^---\r?\n([\s\S]*?)\r?\n---/

export function parseFrontmatter(content: string | undefined): Record<string, unknown> {
  if (!content) {
    return {}
  }
  const match = FRONTMATTER_RE.exec(content)
  if (!match) {
    return {}
  }
  // The editor reads this live from a possibly-mid-edit file, so malformed YAML
  // (e.g. a duplicate mapping key — js-yaml's load() rejects it by throwing) is an
  // expected transient state, not an exception to propagate: degrade to {} so a bad
  // keystroke never tears down the render tree. The engine lint still surfaces the
  // real error as an editor marker.
  let parsed: unknown
  try {
    parsed = yaml.load(match[1])
  } catch {
    return {}
  }
  return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
    ? parsed as Record<string, unknown>
    : {}
}

export function schemaObject(value: unknown): JsonSchemaObject | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as JsonSchemaObject
    : null
}

export function ioSchemaOf(frontmatter: Record<string, unknown>, side: IoSide): JsonSchemaObject | null {
  const io = schemaObject(frontmatter.io)
  return io ? schemaObject(io[side]) : null
}

export function ioPropertiesOf(frontmatter: Record<string, unknown>, side: IoSide): Record<string, unknown> {
  const schema = ioSchemaOf(frontmatter, side)
  const properties = schema ? schemaObject(schema.properties) : null
  return properties ?? {}
}

const PHASE_NODE_FILES = ['SKILL.md', 'LOGIC.md', 'SUBGRAPH.md'] as const

/** Locate the phase's node file (exactly one of SKILL/LOGIC/SUBGRAPH.md). */
export function phaseNodeFileContent(skillDetail: SkillDetail | undefined, phaseId: string): string | undefined {
  const files = skillDetail?.files ?? {}
  for (const name of PHASE_NODE_FILES) {
    const content = files[`phases/${phaseId}/${name}`]
    if (typeof content === 'string') {
      return content
    }
  }
  return undefined
}

export function rootGraphFrontmatter(skillDetail: SkillDetail | undefined): Record<string, unknown> {
  return parseFrontmatter(skillDetail?.files?.['GRAPH.md'])
}

/**
 * True when a property subschema describes an object, so its own `properties`
 * are addressable sub-paths of the value (nested addressing, PM 2026-07-03).
 * Mirrors the engine `_is_object_schema` and backend `_is_object_schema` so all
 * three layers agree on what counts as a nestable field.
 */
export function isObjectSchema(schema: JsonSchemaObject): boolean {
  const schemaType = schema.type
  if (schemaType === 'object' || (Array.isArray(schemaType) && schemaType.includes('object'))) {
    return true
  }
  return schemaObject(schema.properties) != null
}

export interface FieldPathRow {
  /** Leaf segment for display, e.g. `aa_number`. */
  name: string
  /** Dotted full path identity, e.g. `chapter.aa_number`. */
  path: string
  /** Nesting depth (0 = top-level) for tree indentation. */
  depth: number
  schema: JsonSchemaObject
  /** True when this is an object field with at least one nested property. */
  hasChildren: boolean
}

/**
 * Depth-first field descriptors for a `properties` map: every addressable dotted
 * path (parent object paths AND their descendant leaves), in stable pre-order so
 * a parent always precedes its children. The single source the i/o config tree,
 * reconciliation, and the edge-dot inference share, mirroring the backend
 * `_flatten_field_paths` and the engine's recursive required walk.
 */
export function fieldPathRows(
  properties: Record<string, unknown>,
  prefix = '',
  depth = 0,
): FieldPathRow[] {
  const rows: FieldPathRow[] = []
  for (const [name, raw] of Object.entries(properties)) {
    const schema = schemaObject(raw) ?? {}
    const path = prefix ? `${prefix}.${name}` : name
    const nested = isObjectSchema(schema) ? schemaObject(schema.properties) : null
    const hasChildren = nested != null && Object.keys(nested).length > 0
    rows.push({ name, path, depth, schema, hasChildren })
    if (nested) {
      rows.push(...fieldPathRows(nested, path, depth + 1))
    }
  }
  return rows
}

/** Every addressable dotted path (parent + descendants) of a `properties` map. */
export function flattenFieldPaths(properties: Record<string, unknown>): string[] {
  return fieldPathRows(properties).map((row) => row.path)
}
