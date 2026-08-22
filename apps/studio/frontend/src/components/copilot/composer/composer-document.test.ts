/** What the composer's document turns into when the user hits send.
 *
 * Design: `copilot-assist/mvp1-alignment.md` F4 + decisions COPILOT_ASSIST-8
 * (a mention's identity is `(kind, ref)`, given by the frontend) and
 * COPILOT_ASSIST-10 ① (a pill's text form is `@<label>`, where the pill sat).
 *
 * The rules these tests hold the serializer to:
 *   * the sentence stays a sentence — a pill leaves `@label` behind, in place;
 *   * identity travels in `mentions[]` only, never in the text;
 *   * the same object mentioned twice is sent twice — collapsing it is the
 *     backend's job, because the injection budget is the backend's rule.
 */
import { describe, expect, it } from 'vitest'

import { composerValueFromDoc, isEmptyComposerDoc } from './composer-document'

function doc(...paragraphs: unknown[][]) {
  return {
    type: 'doc',
    content: paragraphs.map((content) => ({ type: 'paragraph', content })),
  }
}

const text = (value: string) => ({ type: 'text', text: value })
const mention = (kind: string, ref: string, label: string) => ({
  type: 'mention',
  attrs: { kind, ref, label },
})

describe('composerValueFromDoc', () => {
  it('carries plain typing through untouched', () => {
    expect(composerValueFromDoc(doc([text('why is this phase slow?')]))).toEqual({
      text: 'why is this phase slow?',
      mentions: [],
    })
  })

  it('leaves `@label` where the pill sat, so the sentence still reads as one', () => {
    const value = composerValueFromDoc(
      doc([text('look at '), mention('phase', 'plan', 'plan'), text(' and tell me why')]),
    )
    expect(value.text).toBe('look at @plan and tell me why')
    expect(value.mentions).toEqual([{ kind: 'phase', ref: 'plan', label: 'plan' }])
  })

  it('puts identity in mentions and only the label in the text', () => {
    // The user saw "segment" — a phase inside a subgraph whose ref is the long
    // form. COPILOT_ASSIST-8: label never locates, so the text shows the short
    // name the user read while `ref` carries the address.
    const value = composerValueFromDoc(
      doc([mention('phase', 'chunking/segment', 'segment'), text(' is the one')]),
    )
    expect(value.text).toBe('@segment is the one')
    expect(value.mentions).toEqual([
      { kind: 'phase', ref: 'chunking/segment', label: 'segment' },
    ])
  })

  it('sends the same object twice when the user wrote it twice', () => {
    // COPILOT_ASSIST-10 ②: collapsing duplicates belongs to the backend, which
    // owns the shared injection budget. The composer reports what was typed.
    const value = composerValueFromDoc(
      doc([
        mention('file', 'GRAPH.md', 'GRAPH.md'),
        text(' vs '),
        mention('file', 'GRAPH.md', 'GRAPH.md'),
      ]),
    )
    expect(value.text).toBe('@GRAPH.md vs @GRAPH.md')
    expect(value.mentions).toHaveLength(2)
  })

  it('keeps every kind of mention, in the order they appear', () => {
    const value = composerValueFromDoc(
      doc([
        mention('dot', 'plan.outline', 'plan.outline'),
        text(' '),
        mention('error', '[F-v3-io-missing]@GRAPH.md:12', 'F-v3-io-missing'),
        text(' '),
        mention('trace', 'run-7#31', 'llm_call#31'),
      ]),
    )
    expect(value.mentions.map((item) => item.kind)).toEqual(['dot', 'error', 'trace'])
    expect(value.text).toBe('@plan.outline @F-v3-io-missing @llm_call#31')
  })

  it('joins paragraphs with a newline, the way the user split them', () => {
    const value = composerValueFromDoc(doc([text('first')], [text('second')]))
    expect(value.text).toBe('first\nsecond')
  })

  it('reads an untouched editor as empty rather than as a blank message', () => {
    expect(isEmptyComposerDoc(doc([]))).toBe(true)
    expect(isEmptyComposerDoc(doc([text('   ')]))).toBe(true)
    expect(isEmptyComposerDoc(doc([text('hi')]))).toBe(false)
  })

  it('counts a lone pill as something worth sending', () => {
    // A message that is only "@GRAPH.md" is a real ask ("look at this"), and the
    // send button keying off trimmed TEXT alone would grey out on it.
    expect(isEmptyComposerDoc(doc([mention('file', 'GRAPH.md', 'GRAPH.md')]))).toBe(false)
  })
})
