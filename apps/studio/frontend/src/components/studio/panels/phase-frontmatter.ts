import yaml from 'js-yaml'
import type { JsonValue } from '@/api/types'
import { isRecord } from '@/utils/errors'

export type PhaseFrontmatterKind = 'logic' | 'skill' | 'subgraph'
export type PhaseFrontmatterErrorReason = 'missing-frontmatter' | 'unterminated-frontmatter' | 'invalid-yaml' | 'non-object-frontmatter'

export interface PhaseFrontmatterFormData {
  name: string
  mode: string
  pythonCallable: string
  systemPrompt: string
  exitContract: string
  tools: string
  targetSkill: string
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

const EMPTY_FORM: PhaseFrontmatterFormData = {
  name: '',
  mode: 'logic',
  pythonCallable: '',
  systemPrompt: '',
  exitContract: '',
  tools: '',
  targetSkill: '',
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

export function phaseFrontmatterToForm(frontmatter: Partial<PhaseFrontmatter>, body = ''): PhaseFrontmatterFormData {
  return {
    name: stringValue(frontmatter.name),
    mode: stringValue(frontmatter.mode) || inferKind(frontmatter),
    pythonCallable: xmlBlockValue(body, 'python_callable'),
    systemPrompt: xmlBlockValue(body, 'system_prompt'),
    exitContract: xmlBlockValue(body, 'exit_contract'),
    tools: linesValue(frontmatter.tools),
    targetSkill: stringValue(frontmatter.target_skill),
  }
}

export function applyPhaseFrontmatterForm(
  markdown: string,
  form: PhaseFrontmatterFormData = EMPTY_FORM,
): ApplyPhaseFrontmatterResult {
  const parsed = parsePhaseFrontmatter(markdown)
  if (!parsed.ok) {
    return {
      ok: false,
      reason: parsed.reason,
      message: parsed.message,
    }
  }

  const nextFrontmatter = frontmatterFromForm(parsed.frontmatter, form)
  const kind = inferKind({ ...nextFrontmatter, mode: form.mode, target_skill: form.targetSkill })
  const dumped = yaml.dump(nextFrontmatter, {
    lineWidth: 120,
    noRefs: true,
    sortKeys: false,
    styles: { '!!null': 'empty' },
  }).trimEnd()
  const nextBody = bodyFromForm(parsed.body, form, kind)
  const body = nextBody.length > 0 ? `\n${nextBody}` : '\n'
  return { ok: true, markdown: `---\n${dumped}\n---${body}` }
}

export function phaseKindFromFrontmatter(frontmatter: Partial<PhaseFrontmatter>): PhaseFrontmatterKind {
  return inferKind(frontmatter)
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

function frontmatterFromForm(frontmatter: PhaseFrontmatter, form: PhaseFrontmatterFormData): PhaseFrontmatter {
  const next: PhaseFrontmatter = { ...frontmatter }
  const kind = inferKind({ ...frontmatter, mode: form.mode, target_skill: form.targetSkill })

  setOptionalString(next, 'name', form.name)
  setOptionalString(next, 'mode', form.mode)

  if (kind === 'logic') {
    delete next.validator
    delete next.execute_steps
    delete next.llm_role
    delete next.model_override
    delete next.prompt
    delete next.user_prompt_template
    delete next.agent_tools
    delete next.sub_skill_ref
    delete next.tools
    delete next.target_skill
    return next
  }

  if (kind === 'subgraph') {
    setOptionalString(next, 'target_skill', form.targetSkill)
    delete next.validator
    delete next.execute_steps
    delete next.llm_role
    delete next.model_override
    delete next.prompt
    delete next.user_prompt_template
    delete next.agent_tools
    delete next.sub_skill_ref
    delete next.tools
    return next
  }

  setOptionalList(next, 'tools', form.tools)
  delete next.validator
  delete next.execute_steps
  delete next.llm_role
  delete next.model_override
  delete next.prompt
  delete next.user_prompt_template
  delete next.agent_tools
  delete next.sub_skill_ref
  delete next.target_skill
  return next
}

function inferKind(frontmatter: Partial<PhaseFrontmatter>): PhaseFrontmatterKind {
  const mode = stringValue(frontmatter.mode)
  if (mode === 'subgraph' || stringValue(frontmatter.target_skill) || stringValue(frontmatter.sub_skill_ref)) {
    return 'subgraph'
  }
  if (mode === 'skill' || mode === 'llm') {
    return 'skill'
  }
  return 'logic'
}

function bodyFromForm(body: string, form: PhaseFrontmatterFormData, kind: PhaseFrontmatterKind): string {
  const next = removeXmlBlock(removeXmlBlock(removeXmlBlock(body, 'python_callable'), 'system_prompt'), 'exit_contract').trimStart()
  if (kind === 'logic') {
    return prependXmlBlocks(next, [['python_callable', form.pythonCallable]])
  }
  if (kind === 'skill') {
    return prependXmlBlocks(next, [
      ['system_prompt', form.systemPrompt],
      ['exit_contract', form.exitContract],
    ])
  }
  return next
}

function prependXmlBlocks(body: string, blocks: Array<[tag: string, value: string]>): string {
  const rendered = blocks
    .map(([tag, value]) => xmlBlock(tag, value))
    .filter(Boolean)
    .join('\n\n')
  if (!rendered) {
    return body
  }
  return body ? `${rendered}\n\n${body}` : `${rendered}\n`
}

function xmlBlock(tag: string, value: string): string {
  const trimmed = value.trim()
  return trimmed ? `<${tag}>\n${trimmed}\n</${tag}>` : ''
}

function xmlBlockValue(body: string, tag: string): string {
  const match = xmlBlockRegex(tag).exec(body)
  return match?.[1]?.trim() ?? ''
}

function removeXmlBlock(body: string, tag: string): string {
  return body.replace(xmlBlockRegex(tag), '').replace(/\n{3,}/g, '\n\n')
}

function xmlBlockRegex(tag: string): RegExp {
  return new RegExp(`<${tag}>\\s*([\\s\\S]*?)\\s*<\\/${tag}>\\n*`, 'm')
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function linesValue(value: unknown): string {
  if (!Array.isArray(value)) {
    return ''
  }
  return value.filter((item): item is string => typeof item === 'string').join('\n')
}

function setOptionalString(target: PhaseFrontmatter, key: string, value: string): void {
  const trimmed = value.trim()
  if (trimmed) {
    target[key] = trimmed
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
