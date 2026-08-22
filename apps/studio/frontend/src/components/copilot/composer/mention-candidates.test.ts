/** What the `@` menu offers, and in what order.
 *
 * Design: `copilot-assist/mvp1-alignment.md` F4 ① (five kinds, fuzzy filter,
 * keyboard navigation) + decision COPILOT_ASSIST-10 ③ (grouped in F4's order,
 * at most 8 per group, and a truncated group SAYS how many more matched).
 *
 * The rule behind the cap and the count is F13's: a screen must not let the
 * reader draw a wrong conclusion. A list that quietly stops at eight reads as
 * "your phase isn't here" when the phase is simply on line nine.
 */
import { describe, expect, it } from 'vitest'

import type { GraphTopologyItem, LintError } from '../../../api/types'
import { buildMentionCandidates, filterMentionCandidates } from './mention-candidates'

function phase(id: string, outputs: string[] = []): GraphTopologyItem {
  return {
    id,
    src: `${id}/LOGIC.md`,
    depends_on: [],
    mode: 'logic',
    io_fields: {
      inputs: {},
      outputs: Object.fromEntries(outputs.map((key) => [key, { type: 'string' }])),
    },
  }
}

function diagnostic(code: string, file: string, line: number | null): LintError {
  return {
    error_code: code,
    severity: 'error',
    message: `${code} says something`,
    phase_name: null,
    file,
    line,
    column: null,
  }
}

const SOURCES = {
  filePaths: ['GRAPH.md', 'plan/LOGIC.md', 'draft/LOGIC.md'],
  phases: [phase('plan', ['outline']), phase('draft', ['prose', 'notes'])],
  diagnostics: [diagnostic('F-v3-io-missing', 'GRAPH.md', 12)],
  trace: {
    runId: 'run-7',
    events: [
      { event_type: 'phase_started', payload: { phase_name: 'plan' } },
      { event_type: 'llm_call', payload: { phase_name: 'plan' } },
    ],
  },
} satisfies Parameters<typeof buildMentionCandidates>[0]

describe('buildMentionCandidates', () => {
  const candidates = buildMentionCandidates(SOURCES)
  const ofKind = (kind: string) => candidates.filter((item) => item.kind === kind)

  it('offers one candidate per workspace file, addressed by its path', () => {
    expect(ofKind('file').map((item) => item.ref)).toEqual([
      'GRAPH.md',
      'plan/LOGIC.md',
      'draft/LOGIC.md',
    ])
  })

  it('offers one candidate per phase, addressed by its phase id', () => {
    expect(ofKind('phase').map((item) => item.ref)).toEqual(['plan', 'draft'])
  })

  it('offers one dot per phase OUTPUT, written `<phase>.<key>`', () => {
    // A dot is a blackboard key, and what a phase puts on the blackboard is its
    // io.outputs — its inputs are somebody else's outputs, already listed there.
    expect(ofKind('dot').map((item) => item.ref)).toEqual([
      'plan.outline',
      'draft.prose',
      'draft.notes',
    ])
  })

  it('addresses a diagnostic by its code AND where it landed', () => {
    // Two `[F-v3-io-missing]` on different lines are two different problems; a
    // ref that is only the code cannot tell the copilot which one was meant.
    expect(ofKind('error')[0]).toMatchObject({
      ref: 'F-v3-io-missing@GRAPH.md:12',
      label: 'F-v3-io-missing',
    })
  })

  it('addresses a trace event as `<run_id>#<event_index>`', () => {
    expect(ofKind('trace').map((item) => item.ref)).toEqual(['run-7#0', 'run-7#1'])
    expect(ofKind('trace')[1].label).toBe('llm_call#1')
  })

  it('offers nothing at all when the workspace has nothing to offer', () => {
    expect(
      buildMentionCandidates({ filePaths: [], phases: [], diagnostics: [], trace: null }),
    ).toEqual([])
  })
})

describe('filterMentionCandidates', () => {
  const candidates = buildMentionCandidates(SOURCES)

  it('groups in the order F4 lists the kinds', () => {
    const groups = filterMentionCandidates(candidates, '')
    expect(groups.map((group) => group.kind)).toEqual(['file', 'phase', 'dot', 'error', 'trace'])
  })

  it('matches loosely and ignores case', () => {
    const groups = filterMentionCandidates(candidates, 'PLN')
    const phases = groups.find((group) => group.kind === 'phase')
    expect(phases?.items.map((item) => item.ref)).toEqual(['plan'])
  })

  it('puts what starts with the query above what merely contains it', () => {
    const groups = filterMentionCandidates(candidates, 'plan')
    const files = groups.find((group) => group.kind === 'file')
    // `plan/LOGIC.md` starts with it; `GRAPH.md` does not match at all.
    expect(files?.items[0].ref).toBe('plan/LOGIC.md')
  })

  it('drops a kind entirely when nothing in it matches', () => {
    const groups = filterMentionCandidates(candidates, 'outline')
    expect(groups.map((group) => group.kind)).toEqual(['dot'])
  })

  it('returns no groups at all when nothing anywhere matches', () => {
    expect(filterMentionCandidates(candidates, 'zzzz')).toEqual([])
  })

  it('caps a group at 8 and says how many more matched', () => {
    const many = buildMentionCandidates({
      filePaths: Array.from({ length: 20 }, (_, index) => `node${index}/LOGIC.md`),
      phases: [],
      diagnostics: [],
      trace: null,
    })
    const files = filterMentionCandidates(many, 'LOGIC')[0]
    expect(files.items).toHaveLength(8)
    expect(files.hiddenCount).toBe(12)
  })

  it('reports nothing hidden when the whole group fits', () => {
    const files = filterMentionCandidates(candidates, 'md')[0]
    expect(files.hiddenCount).toBe(0)
  })
})
