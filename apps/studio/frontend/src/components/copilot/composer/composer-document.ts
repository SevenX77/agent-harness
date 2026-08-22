/** The composer's document, read out as the two things a turn carries.
 *
 * Design: `docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md`
 * F4 ② + decisions COPILOT_ASSIST-8 and COPILOT_ASSIST-10 ①.
 *
 * A turn carries a sentence (`user_message`) and a list of objects the user
 * picked (`mentions[]`). The pill in the editor is one object appearing in both
 * roles at once, and this module is where it splits: the sentence keeps
 * `@<label>` in the pill's position so it still reads as a sentence, while the
 * address `(kind, ref)` goes to `mentions[]` and NOWHERE else. Nothing
 * downstream may recover identity by parsing the text — that is the same
 * "label never locates" rule COPILOT_ASSIST-8 states for the wire.
 *
 * The input is tiptap's `getJSON()`, which is plain data, so everything here
 * stays a pure function of it.
 */
import type { CopilotMention } from '../../../types/copilot'

/** The tiptap node name the mention Node registers under. */
export const MENTION_NODE_NAME = 'mention'

/** A node in tiptap's JSON document, narrowed to what this composer can hold. */
interface ComposerDocNode {
  type?: string
  text?: string
  attrs?: Record<string, unknown>
  content?: ComposerDocNode[]
}

export interface ComposerValue {
  text: string
  mentions: CopilotMention[]
}

export const EMPTY_COMPOSER_VALUE: ComposerValue = { text: '', mentions: [] }

function asDocNode(value: unknown): ComposerDocNode | null {
  return typeof value === 'object' && value !== null ? (value as ComposerDocNode) : null
}

function mentionFromAttrs(attrs: Record<string, unknown> | undefined): CopilotMention | null {
  const kind = attrs?.kind
  const ref = attrs?.ref
  const label = attrs?.label
  if (typeof kind !== 'string' || typeof ref !== 'string' || typeof label !== 'string') {
    return null
  }
  return { kind: kind as CopilotMention['kind'], ref, label }
}

/** Append one inline node's contribution to the sentence and the mention list. */
function readInline(node: ComposerDocNode, into: { text: string; mentions: CopilotMention[] }) {
  if (node.type === MENTION_NODE_NAME) {
    const mention = mentionFromAttrs(node.attrs)
    if (mention) {
      into.text += `@${mention.label}`
      into.mentions.push(mention)
    }
    return
  }
  if (typeof node.text === 'string') {
    into.text += node.text
    return
  }
  for (const child of node.content ?? []) {
    readInline(child, into)
  }
}

/** Split one editor document into the sentence and the objects it names. */
export function composerValueFromDoc(doc: unknown): ComposerValue {
  const root = asDocNode(doc)
  if (!root) return EMPTY_COMPOSER_VALUE
  const mentions: CopilotMention[] = []
  const blocks: string[] = []
  for (const block of root.content ?? []) {
    const collected = { text: '', mentions }
    for (const inline of block.content ?? []) {
      readInline(inline, collected)
    }
    blocks.push(collected.text)
  }
  return { text: blocks.join('\n'), mentions }
}

/**
 * Whether there is anything to send.
 *
 * Keyed off the serialized sentence rather than off "is the doc one empty
 * paragraph": a document holding only a pill serializes to `@GRAPH.md`, which
 * is a real ask ("look at this"), and any emptiness test that only looked at
 * text NODES would grey the send button out on it.
 */
export function isEmptyComposerDoc(doc: unknown): boolean {
  return composerValueFromDoc(doc).text.trim().length === 0
}
