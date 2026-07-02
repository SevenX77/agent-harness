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

export interface PhaseSubgraphRef {
  name: string
  path: string
  description: string
}

export interface PhaseResourceRef {
  id: string
  path: string
  summary: string
}

export type IterateMode = '' | 'batch' | 'loop'
export type IterateMergeMode = 'append' | 'extend' | 'merge' | 'replace'

export interface PhaseIterateFormData {
  mode: IterateMode
  over: string
  itemVar: string
  rangeStart: string
  rangeEnd: string
  concurrency: string
  accumulateVar: string
  accumulateInit: string
  accumulateFrom: string
  accumulateMerge: IterateMergeMode
}

export interface PhaseFrontmatterFormData {
  // agent (SKILL.md)
  llmRole: string
  // Priority switch: true = the graph-level default llm_role wins over this
  // node's own llmRole; the node value itself is preserved untouched.
  useGraphLlmRole: boolean
  tools: string
  subagents: PhaseSubagentRef[]
  subgraphs: PhaseSubgraphRef[]
  references: PhaseResourceRef[]
  examples: PhaseResourceRef[]
  maxIterations: string
  // logic (LOGIC.md)
  actions: string
  // subgraph (SUBGRAPH.md)
  path: string
  // shared (agent + logic + subgraph)
  validator: boolean
  // shared (agent + logic + subgraph)
  allowSequentialOverwrite: string
  iterate: PhaseIterateFormData
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
  useGraphLlmRole: false,
  tools: '',
  subagents: [],
  subgraphs: [],
  references: [],
  examples: [],
  maxIterations: '',
  actions: '',
  path: '',
  validator: false,
  allowSequentialOverwrite: '',
  iterate: emptyIterateForm(),
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
    useGraphLlmRole: booleanValue(frontmatter.use_graph_llm_role),
    tools: linesValue(frontmatter.tools),
    subagents: subagentsValue(frontmatter.subagents),
    subgraphs: subgraphsValue(frontmatter.subgraphs),
    references: resourcesValue(frontmatter.references),
    examples: resourcesValue(frontmatter.examples),
    maxIterations: numberStringValue(frontmatter.max_iterations),
    actions: linesValue(frontmatter.actions),
    path: stringValue(frontmatter.path),
    validator: booleanValue(frontmatter.validator),
    allowSequentialOverwrite: linesValue(frontmatter.allow_sequential_overwrite),
    iterate: iterateValue(frontmatter.iterate, frontmatter.batch),
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
  return { ok: true, markdown: serializePhaseMarkdown(nextFrontmatter, parsed.body) }
}

export function applyPhaseName(markdown: string, nextName: string): ApplyPhaseFrontmatterResult {
  const parsed = parsePhaseFrontmatter(markdown)
  if (!parsed.ok) {
    return {
      ok: false,
      reason: parsed.reason,
      message: parsed.message,
    }
  }
  const trimmed = nextName.trim()
  if (!trimmed) {
    return { ok: false, reason: 'non-object-frontmatter', message: 'Phase name is required.' }
  }
  return {
    ok: true,
    markdown: serializePhaseMarkdown({ ...parsed.frontmatter, name: trimmed }, parsed.body),
  }
}

/**
 * Toggle just the `validator` flag on a phase file, preserving everything else.
 * Used when Studio creates a `validator.py` (enable) — separate from the form save
 * path so it can run as a standalone file action. Default `false` is dropped, never
 * written as an explicit `validator: false`.
 */
export function applyPhaseValidator(markdown: string, enabled: boolean): ApplyPhaseFrontmatterResult {
  const parsed = parsePhaseFrontmatter(markdown)
  if (!parsed.ok) {
    return {
      ok: false,
      reason: parsed.reason,
      message: parsed.message,
    }
  }
  const next: PhaseFrontmatter = { ...parsed.frontmatter }
  setBoolean(next, 'validator', enabled)
  return {
    ok: true,
    markdown: serializePhaseMarkdown(next, parsed.body),
  }
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
    setBoolean(next, 'use_graph_llm_role', form.useGraphLlmRole)
    setOptionalList(next, 'tools', form.tools)
    setSubagents(next, form.subagents)
    setSubgraphs(next, form.subgraphs)
    setResourceList(next, 'references', form.references)
    setResourceList(next, 'examples', form.examples)
    setBoolean(next, 'validator', form.validator)
    setMaxIterations(next, form.maxIterations)
    setOptionalList(next, 'allow_sequential_overwrite', form.allowSequentialOverwrite)
    setIterate(next, form.iterate)
    return next
  }

  if (kind === 'logic') {
    setOptionalList(next, 'actions', form.actions)
    setBoolean(next, 'validator', form.validator)
    setOptionalList(next, 'allow_sequential_overwrite', form.allowSequentialOverwrite)
    setIterate(next, form.iterate)
    return next
  }

  delete next.target_skill
  delete next.targetSkill
  setOptionalString(next, 'path', form.path)
  setBoolean(next, 'validator', form.validator)
  setOptionalList(next, 'allow_sequential_overwrite', form.allowSequentialOverwrite)
  setIterate(next, form.iterate)
  return next
}

export function serializePhaseMarkdown(frontmatter: PhaseFrontmatter, bodyContent: string): string {
  const dumped = yaml.dump(frontmatter, {
    lineWidth: 120,
    noRefs: true,
    sortKeys: false,
    styles: { '!!null': 'empty' },
  }).trimEnd()
  const trimmedBody = bodyContent.replace(/^\n+/, '')
  const body = trimmedBody.length > 0 ? `\n${trimmedBody}` : '\n'
  return `---\n${dumped}\n---${body}`
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function booleanValue(value: unknown): boolean {
  return value === true
}

function numberStringValue(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : ''
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

function emptyIterateForm(): PhaseIterateFormData {
  return {
    mode: '',
    over: '',
    itemVar: '',
    rangeStart: '',
    rangeEnd: '',
    concurrency: '',
    accumulateVar: '',
    accumulateInit: '[]',
    accumulateFrom: '',
    accumulateMerge: 'append',
  }
}

function yamlInlineValue(value: unknown): string {
  if (value === undefined) {
    return ''
  }
  return yaml.dump(value, {
    flowLevel: 0,
    lineWidth: 120,
    noRefs: true,
    sortKeys: false,
    styles: { '!!null': 'empty' },
  }).trim()
}

function iterateValue(iterate: unknown, legacyBatch: unknown): PhaseIterateFormData {
  if (isRecord(iterate)) {
    const mode = iterate.mode === 'batch' || iterate.mode === 'loop' ? iterate.mode : ''
    const range = Array.isArray(iterate.range) ? iterate.range : []
    const accumulate = isRecord(iterate.accumulate) ? iterate.accumulate : {}
    return {
      ...emptyIterateForm(),
      mode,
      over: stringValue(iterate.over),
      itemVar: stringValue(iterate.item_var),
      rangeStart: numberStringValue(range[0]),
      rangeEnd: numberStringValue(range[1]),
      concurrency: numberStringValue(iterate.concurrency),
      accumulateVar: stringValue(accumulate.var),
      accumulateInit: Object.prototype.hasOwnProperty.call(accumulate, 'init')
        ? yamlInlineValue(accumulate.init)
        : '[]',
      accumulateFrom: stringValue(accumulate.from),
      accumulateMerge: mergeValue(accumulate.merge),
    }
  }

  if (isRecord(legacyBatch)) {
    return {
      ...emptyIterateForm(),
      mode: 'batch',
      over: stringValue(legacyBatch.iterator),
      itemVar: stringValue(legacyBatch.item_var),
      concurrency: numberStringValue(legacyBatch.concurrency),
    }
  }

  return emptyIterateForm()
}

function mergeValue(value: unknown): IterateMergeMode {
  return value === 'extend' || value === 'merge' || value === 'replace' ? value : 'append'
}

function intValue(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) {
    return null
  }
  const parsed = Number.parseInt(trimmed, 10)
  return Number.isFinite(parsed) && String(parsed) === trimmed ? parsed : null
}

function parseYamlValue(value: string): JsonValue {
  const trimmed = value.trim()
  if (!trimmed) {
    return []
  }
  try {
    const parsed = yaml.load(trimmed)
    if (parsed == null || typeof parsed === 'string' || typeof parsed === 'number' || typeof parsed === 'boolean' || Array.isArray(parsed) || isRecord(parsed)) {
      return parsed as JsonValue
    }
  } catch {
    return trimmed
  }
  return trimmed
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

function subgraphsValue(value: unknown): PhaseSubgraphRef[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.flatMap((item) => {
    if (!isRecord(item)) {
      return []
    }
    return [{
      name: stringValue(item.name),
      path: stringValue(item.path),
      description: stringValue(item.description),
    }]
  })
}

function resourcesValue(value: unknown): PhaseResourceRef[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.flatMap((item) => {
    if (!isRecord(item)) {
      return []
    }
    return [{
      id: stringValue(item.id),
      path: stringValue(item.path),
      summary: stringValue(item.summary),
    }]
  })
}

// Agent-only subgraph registry items (AgentRegistryItem: name/path/description).
// Engine requires path to be absolute; the form/UI carries that constraint, this
// serializer only trims and drops fully-empty rows so blanks never pollute YAML.
function setSubgraphs(target: PhaseFrontmatter, subgraphs: PhaseSubgraphRef[]): void {
  const cleaned = subgraphs
    .map((entry) => ({
      name: entry.name.trim(),
      path: entry.path.trim(),
      description: entry.description.trim(),
    }))
    .filter((entry) => entry.name || entry.path || entry.description)
  if (cleaned.length > 0) {
    target.subgraphs = cleaned
  } else {
    delete target.subgraphs
  }
}

// Shared serializer for the agent `references` / `examples` arrays — both are
// ReferenceSpec/ExampleSpec shaped (id/path/summary).
function setResourceList(target: PhaseFrontmatter, key: 'references' | 'examples', items: PhaseResourceRef[]): void {
  const cleaned = items
    .map((entry) => ({
      id: entry.id.trim(),
      path: entry.path.trim(),
      summary: entry.summary.trim(),
    }))
    .filter((entry) => entry.id || entry.path || entry.summary)
  if (cleaned.length > 0) {
    target[key] = cleaned
  } else {
    delete target[key]
  }
}

function setMaxIterations(target: PhaseFrontmatter, value: string): void {
  const parsed = intValue(value)
  if (parsed != null) {
    target.max_iterations = parsed
  } else {
    delete target.max_iterations
  }
}

function setIterate(target: PhaseFrontmatter, iterate: PhaseIterateFormData): void {
  delete target.batch
  if (iterate.mode !== 'batch' && iterate.mode !== 'loop') {
    delete target.iterate
    return
  }

  const next: PhaseFrontmatter = {
    mode: iterate.mode,
    over: iterate.over.trim(),
    item_var: iterate.itemVar.trim(),
  }

  const rangeStart = intValue(iterate.rangeStart)
  const rangeEnd = intValue(iterate.rangeEnd)
  if (rangeStart != null && rangeEnd != null) {
    next.range = [rangeStart, rangeEnd]
  }

  const concurrency = intValue(iterate.concurrency)
  if (iterate.mode === 'batch' && concurrency != null) {
    next.concurrency = concurrency
  }

  if (iterate.mode === 'loop') {
    next.accumulate = {
      var: iterate.accumulateVar.trim(),
      init: parseYamlValue(iterate.accumulateInit),
      from: iterate.accumulateFrom.trim(),
      merge: iterate.accumulateMerge,
    }
  }

  target.iterate = next
}
