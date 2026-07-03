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
