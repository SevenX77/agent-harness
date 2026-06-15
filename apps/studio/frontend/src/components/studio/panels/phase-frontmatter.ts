import yaml from 'js-yaml'
import type { JsonValue } from '@/api/types'
import { isRecord } from '@/utils/errors'

export type PhaseFrontmatterKind = 'logic' | 'agent' | 'subgraph'
export type PhaseFrontmatterErrorReason = 'missing-frontmatter' | 'unterminated-frontmatter' | 'invalid-yaml' | 'non-object-frontmatter'

export interface PhaseSubagentRef {
  name: string
  target_skill: string
  description: string
}

export interface PhaseFrontmatterFormData {
  // agent (SKILL.md)
  llmRole: string
  tools: string
  subagents: PhaseSubagentRef[]
  // logic (LOGIC.md)
  actions: string
  // subgraph (SUBGRAPH.md)
  path: string
  // shared (logic + subgraph)
  validator: boolean
}

export type PhaseFrontmatter = Record<string, JsonValue>

export type ParsePhaseFrontmatterResult =
  | {
    ok: true
    frontmatter: PhaseFrontmatter
    body: string
  }
  | {
    ok: false
    reason: PhaseFrontmatterErrorReason
    message: string
  }

export type ApplyPhaseFrontmatterResult =
  | { ok: true; markdown: string }
  | { ok: false; reason: PhaseFrontmatterErrorReason; message: string }

export const EMPTY_FORM: PhaseFrontmatterFormData = {
  llmRole: '',
  tools: '',
  subagents: [],
  actions: '',
  path: '',
  validator: false,
}

export function parsePhaseFrontmatter(markdown: string): ParsePhaseFrontmatterResult {
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
        message: 'Phase frontmatter must be a YAML object.',
      }
    }
    return { ok: true, frontmatter: loaded as PhaseFrontmatter, body: split.body }
  } catch (error) {
    return {
      ok: false,
      reason: 'invalid-yaml',
      message: error instanceof Error ? error.message : String(error),
    }
  }
}

export function phaseFrontmatterToForm(frontmatter: Partial<PhaseFrontmatter>): PhaseFrontmatterFormData {
  return {
    llmRole: stringValue(frontmatter.llm_role),
    tools: linesValue(frontmatter.tools),
    subagents: subagentsValue(frontmatter.subagents),
    actions: linesValue(frontmatter.actions),
    path: stringValue(frontmatter.path),
    validator: booleanValue(frontmatter.validator),
  }
}

/**
 * Serialize the whitelisted fields for `kind` back into the source markdown.
 *
 * Round-trip contract: parsed frontmatter + body are preserved; only the
 * whitelisted fields for the given node kind are set. Keys outside the
 * whitelist (`name`, `io`, `llm_role` when not an agent, and any unknown key)
 * are never touched, so saving never destroys data the form cannot edit.
 */
export function applyPhaseFrontmatterForm(
  markdown: string,
  form: PhaseFrontmatterFormData,
  kind: PhaseFrontmatterKind,
): ApplyPhaseFrontmatterResult {
  const parsed = parsePhaseFrontmatter(markdown)
  if (!parsed.ok) {
    return {
      ok: false,
      reason: parsed.reason,
      message: parsed.message,
    }
  }

  const nextFrontmatter = frontmatterFromForm(parsed.frontmatter, form, kind)
  const dumped = yaml.dump(nextFrontmatter, {
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
      message: 'Phase file does not contain YAML frontmatter.',
    }
  }

  const endLine = lines.findIndex((line, index) => index > 0 && line.trim() === '---')
  if (endLine < 0) {
    return {
      ok: false,
      reason: 'unterminated-frontmatter',
      message: 'Phase frontmatter is missing a closing delimiter.',
    }
  }

  return {
    ok: true,
    frontmatter: lines.slice(1, endLine).join('\n'),
    body: lines.slice(endLine + 1).join('\n'),
  }
}

function frontmatterFromForm(
  frontmatter: PhaseFrontmatter,
  form: PhaseFrontmatterFormData,
  kind: PhaseFrontmatterKind,
): PhaseFrontmatter {
  const next: PhaseFrontmatter = { ...frontmatter }

  if (kind === 'agent') {
    setOptionalString(next, 'llm_role', form.llmRole)
    setOptionalList(next, 'tools', form.tools)
    setSubagents(next, form.subagents)
    return next
  }

  if (kind === 'logic') {
    setOptionalList(next, 'actions', form.actions)
    setBoolean(next, 'validator', form.validator)
    return next
  }

  setOptionalString(next, 'path', form.path)
  setBoolean(next, 'validator', form.validator)
  return next
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function booleanValue(value: unknown): boolean {
  return value === true
}

function linesValue(value: unknown): string {
  if (!Array.isArray(value)) {
    return ''
  }
  return value.filter((item): item is string => typeof item === 'string').join('\n')
}

function subagentsValue(value: unknown): PhaseSubagentRef[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.flatMap((item) => {
    if (!isRecord(item)) {
      return []
    }
    return [{
      name: stringValue(item.name),
      target_skill: stringValue(item.target_skill),
      description: stringValue(item.description),
    }]
  })
}

function setOptionalString(target: PhaseFrontmatter, key: string, value: string): void {
  const trimmed = value.trim()
  if (trimmed) {
    target[key] = trimmed
  } else {
    delete target[key]
  }
}

function setBoolean(target: PhaseFrontmatter, key: string, value: boolean): void {
  if (value) {
    target[key] = true
  } else {
    delete target[key]
  }
}

function setOptionalList(target: PhaseFrontmatter, key: string, value: string): void {
  const lines = value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
  if (lines.length > 0) {
    target[key] = lines
  } else {
    delete target[key]
  }
}

function setSubagents(target: PhaseFrontmatter, subagents: PhaseSubagentRef[]): void {
  const cleaned = subagents
    .map((entry) => ({
      name: entry.name.trim(),
      target_skill: entry.target_skill.trim(),
      description: entry.description.trim(),
    }))
    .filter((entry) => entry.name || entry.target_skill || entry.description)
  if (cleaned.length > 0) {
    target.subagents = cleaned
  } else {
    delete target.subagents
  }
}
