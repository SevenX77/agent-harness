import yaml from 'js-yaml'
import type { JsonValue } from '@/api/types'
import { isRecord } from '@/utils/errors'

/**
 * GRAPH.md macro-contract header (n2 atom #22).
 *
 * The header is the integral graph's global contract: name / schema_version /
 * llm_role / description / phases (+ top-level io). FROZEN: there is no `type`
 * field — node type is decided by file name (SKILL/LOGIC/SUBGRAPH.md), so this
 * form never reads, writes, or exposes a `type` entry.
 *
 * The four scalar fields (name / schema_version / llm_role / description) are
 * not topology; they are re-rendered into the GRAPH.md frontmatter and written
 * back directly via doWriteSkillFile with the graph hash. The `phases` list is
 * topology and is serialized through the preserving serialize endpoint, so this
 * module deliberately leaves the `phases` key (and io / body / unknown keys)
 * untouched when applying scalar edits.
 */
export type GraphHeaderErrorReason =
  | 'missing-frontmatter'
  | 'unterminated-frontmatter'
  | 'invalid-yaml'
  | 'non-object-frontmatter'

export interface GraphHeaderFormData {
  name: string
  schemaVersion: string
  llmRole: string
  description: string
  phases: string[]
}

export type GraphHeaderFrontmatter = Record<string, JsonValue>

export type ParseGraphHeaderResult =
  | { ok: true; frontmatter: GraphHeaderFrontmatter; body: string }
  | { ok: false; reason: GraphHeaderErrorReason; message: string }

export type ApplyGraphHeaderResult =
  | { ok: true; markdown: string }
  | { ok: false; reason: GraphHeaderErrorReason; message: string }

export const EMPTY_GRAPH_HEADER: GraphHeaderFormData = {
  name: '',
  schemaVersion: '',
  llmRole: '',
  description: '',
  phases: [],
}

export function parseGraphHeader(markdown: string): ParseGraphHeaderResult {
  const split = splitMarkdownFrontmatter(markdown)
  if (!split.ok) {
    return split
  }

  try {
    const loaded = yaml.load(split.frontmatter)
    if (loaded == null) {
      return { ok: true, frontmatter: {}, body: split.body }
    }
    if (!isRecord(loaded)) {
      return {
        ok: false,
        reason: 'non-object-frontmatter',
        message: 'GRAPH.md frontmatter must be a YAML object.',
      }
    }
    return { ok: true, frontmatter: loaded as GraphHeaderFrontmatter, body: split.body }
  } catch (error) {
    return {
      ok: false,
      reason: 'invalid-yaml',
      message: error instanceof Error ? error.message : String(error),
    }
  }
}

export function graphHeaderToForm(markdown: string): GraphHeaderFormData {
  const parsed = parseGraphHeader(markdown)
  if (!parsed.ok) {
    return EMPTY_GRAPH_HEADER
  }
  const fm = parsed.frontmatter
  return {
    name: stringValue(fm.name),
    schemaVersion: stringValue(fm.schema_version),
    llmRole: stringValue(fm.llm_role),
    description: stringValue(fm.description),
    phases: phasesValue(fm.phases),
  }
}

/**
 * Apply the four scalar header fields back into the GRAPH.md markdown.
 *
 * Round-trip contract: the parsed frontmatter + body are preserved; only
 * name / schema_version / llm_role / description are set. The `phases` key, the
 * top-level `io` block, the markdown body, and any unknown key are never
 * touched — phases changes flow through the serialize endpoint, not here — so
 * saving the header never destroys io / description-body / topology the form
 * does not own. `type` is never emitted (FROZEN).
 */
export function applyGraphHeaderForm(
  markdown: string,
  form: GraphHeaderFormData,
): ApplyGraphHeaderResult {
  const parsed = parseGraphHeader(markdown)
  if (!parsed.ok) {
    return { ok: false, reason: parsed.reason, message: parsed.message }
  }

  const next: GraphHeaderFrontmatter = { ...parsed.frontmatter }
  setRequiredString(next, 'name', form.name)
  setRequiredString(next, 'schema_version', form.schemaVersion)
  setOptionalString(next, 'llm_role', form.llmRole)
  setOptionalString(next, 'description', form.description)

  const dumped = yaml.dump(next, {
    lineWidth: 120,
    noRefs: true,
    sortKeys: false,
    styles: { '!!null': 'empty' },
  }).trimEnd()
  const trimmedBody = parsed.body.replace(/^\n+/, '')
  const body = trimmedBody.length > 0 ? `\n${trimmedBody}` : '\n'
  return { ok: true, markdown: `---\n${dumped}\n---${body}` }
}

function splitMarkdownFrontmatter(markdown: string):
  | { ok: true; frontmatter: string; body: string }
  | { ok: false; reason: 'missing-frontmatter' | 'unterminated-frontmatter'; message: string } {
  const lines = markdown.split('\n')
  if (lines[0]?.trim() !== '---') {
    return {
      ok: false,
      reason: 'missing-frontmatter',
      message: 'GRAPH.md does not contain YAML frontmatter.',
    }
  }

  const endLine = lines.findIndex((line, index) => index > 0 && line.trim() === '---')
  if (endLine < 0) {
    return {
      ok: false,
      reason: 'unterminated-frontmatter',
      message: 'GRAPH.md frontmatter is missing a closing delimiter.',
    }
  }

  return {
    ok: true,
    frontmatter: lines.slice(1, endLine).join('\n'),
    body: lines.slice(endLine + 1).join('\n'),
  }
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function phasesValue(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((item): item is string => typeof item === 'string')
}

function setRequiredString(target: GraphHeaderFrontmatter, key: string, value: string): void {
  target[key] = value.trim()
}

function setOptionalString(target: GraphHeaderFrontmatter, key: string, value: string): void {
  const trimmed = value.trim()
  if (trimmed) {
    target[key] = trimmed
  } else {
    delete target[key]
  }
}
