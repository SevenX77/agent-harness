/** What the `@` menu can offer, and how a query narrows it.
 *
 * Design: `docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md`
 * F4 ① + decision COPILOT_ASSIST-10 ③.
 *
 * Everything here is a pure function of what the workspace already holds — the
 * menu never fetches. That is not an optimisation: F4 ③ forbids the composer
 * from reaching for context on its own, so the set of nameable objects is
 * exactly the set the surrounding screens are already showing.
 */
import type { GraphTopologyItem, LintError } from '../../../api/types'
import type { CopilotMention } from '../../../types/copilot'

export type MentionKind = CopilotMention['kind']

export interface MentionCandidate {
  kind: MentionKind
  /** Unique within `kind` — the address COPILOT_ASSIST-8 puts on the wire. */
  ref: string
  /** What the user reads, in the menu and then inside the pill. */
  label: string
  /** A second line in the menu: where it lives, or what it says. */
  detail?: string
}

/**
 * One event of the viewed run, narrowed to the two fields the menu shows.
 *
 * Structural rather than `EventEnvelope` so this module does not depend on the
 * transport envelope's shape: what a mention needs from an event is its type and
 * which phase it happened in, and nothing here should break when the envelope
 * grows a field.
 */
export interface MentionTraceEvent {
  event_type: string
  payload?: { phase_name?: string | null } | null
}

export interface MentionSources {
  /** Workspace-relative paths, as `SkillDetail.file_paths` gives them. */
  filePaths: readonly string[]
  phases: readonly GraphTopologyItem[]
  diagnostics: readonly LintError[]
  /** The run whose events are on screen. Null when no run is being viewed. */
  trace: { runId: string; events: readonly MentionTraceEvent[] } | null
}

export interface MentionGroup {
  kind: MentionKind
  items: MentionCandidate[]
  /** How many more matched than the group shows. 0 when everything fit. */
  hiddenCount: number
}

/** F4 ① lists the kinds in this order; the menu keeps it so the vocabulary
 * reads the same everywhere it appears. */
export const MENTION_KIND_ORDER: readonly MentionKind[] = [
  'file',
  'phase',
  'dot',
  'error',
  'trace',
]

/**
 * At most this many rows per kind.
 *
 * A skill with two hundred files would otherwise push phases, dots, errors and
 * trace off the screen entirely, and F4 ① asks the menu to stay under 50ms on a
 * big project. The cap is only safe BECAUSE a truncated group says so — see
 * `hiddenCount`.
 */
export const MENTION_GROUP_LIMIT = 8

function fileCandidates(paths: readonly string[]): MentionCandidate[] {
  return paths.map((path) => ({ kind: 'file' as const, ref: path, label: path }))
}

function phaseCandidates(phases: readonly GraphTopologyItem[]): MentionCandidate[] {
  return phases.map((phase) => ({
    kind: 'phase' as const,
    ref: phase.id,
    label: phase.id,
    detail: phase.mode,
  }))
}

function dotCandidates(phases: readonly GraphTopologyItem[]): MentionCandidate[] {
  // A dot is a blackboard key, and what a phase PUTS on the blackboard is its
  // io.outputs. Its inputs are some other phase's outputs, already listed under
  // that phase — offering both would name every key twice.
  const candidates: MentionCandidate[] = []
  for (const phase of phases) {
    for (const [key, schema] of Object.entries(phase.io_fields?.outputs ?? {})) {
      const type = (schema as { type?: unknown }).type
      candidates.push({
        kind: 'dot',
        ref: `${phase.id}.${key}`,
        label: `${phase.id}.${key}`,
        detail: typeof type === 'string' ? type : undefined,
      })
    }
  }
  return candidates
}

function diagnosticLocation(diagnostic: LintError): string {
  const file = diagnostic.source_path ?? diagnostic.file ?? '-'
  return diagnostic.line === null ? file : `${file}:${diagnostic.line}`
}

function errorCandidates(diagnostics: readonly LintError[]): MentionCandidate[] {
  // Code AND location, because the same code lands more than once in a broken
  // skill: `[F-v3-io-missing]` on line 12 and on line 40 are two problems, and a
  // ref that were only the code could not say which one the user picked.
  return diagnostics.map((diagnostic) => ({
    kind: 'error' as const,
    ref: `${diagnostic.error_code}@${diagnosticLocation(diagnostic)}`,
    label: diagnostic.error_code,
    detail: diagnostic.message,
  }))
}

function traceCandidates(trace: MentionSources['trace']): MentionCandidate[] {
  if (!trace) return []
  return trace.events.map((event, index) => ({
    kind: 'trace' as const,
    ref: `${trace.runId}#${index}`,
    label: `${event.event_type}#${index}`,
    detail: event.payload?.phase_name ?? undefined,
  }))
}

/** Every object this workspace can name right now, grouped kind by kind. */
export function buildMentionCandidates(sources: MentionSources): MentionCandidate[] {
  return [
    ...fileCandidates(sources.filePaths),
    ...phaseCandidates(sources.phases),
    ...dotCandidates(sources.phases),
    ...errorCandidates(sources.diagnostics),
    ...traceCandidates(sources.trace),
  ]
}

function isSubsequence(needle: string, haystack: string): boolean {
  let cursor = 0
  for (const character of haystack) {
    if (character === needle[cursor]) cursor += 1
    if (cursor === needle.length) return true
  }
  return needle.length === 0
}

/**
 * How well one candidate answers the query. 0 means "not an answer at all".
 *
 * The ladder is what a reader expects to see first: the thing whose NAME starts
 * with what they typed, then the thing whose name contains it, then the thing
 * whose address contains it, and last the loose match that lets `pln` find
 * `plan`.
 */
function score(candidate: MentionCandidate, query: string): number {
  const label = candidate.label.toLowerCase()
  const ref = candidate.ref.toLowerCase()
  if (label.startsWith(query)) return 4
  if (label.includes(query)) return 3
  if (ref.includes(query)) return 2
  if (isSubsequence(query, `${label} ${ref}`)) return 1
  return 0
}

/** Narrow the candidates to what the query names, grouped and capped. */
export function filterMentionCandidates(
  candidates: readonly MentionCandidate[],
  query: string,
): MentionGroup[] {
  const needle = query.trim().toLowerCase()
  const groups: MentionGroup[] = []
  for (const kind of MENTION_KIND_ORDER) {
    const ofKind = candidates.filter((candidate) => candidate.kind === kind)
    // An empty query is not a filter, so it must not reorder either: the build
    // order is the order the surrounding screens list these objects in.
    const matched =
      needle.length === 0
        ? ofKind.slice()
        : ofKind
            .map((candidate) => ({ candidate, rank: score(candidate, needle) }))
            .filter((entry) => entry.rank > 0)
            .sort(
              (left, right) =>
                right.rank - left.rank ||
                left.candidate.label.length - right.candidate.label.length ||
                left.candidate.label.localeCompare(right.candidate.label),
            )
            .map((entry) => entry.candidate)
    if (matched.length === 0) continue
    groups.push({
      kind,
      items: matched.slice(0, MENTION_GROUP_LIMIT),
      hiddenCount: Math.max(0, matched.length - MENTION_GROUP_LIMIT),
    })
  }
  return groups
}

/** The whole menu, flattened in the order the keyboard walks it. */
export function flattenMentionGroups(groups: readonly MentionGroup[]): MentionCandidate[] {
  return groups.flatMap((group) => group.items)
}
