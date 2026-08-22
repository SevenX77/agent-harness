/** The composer's document schema: a line of text that can hold mention atoms.
 *
 * Design: `copilot-assist/mvp1-alignment.md` F4 + decision COPILOT_ASSIST-10 ④.
 *
 * Borrowed from ProseMirror: `atom: true` on an inline node, which is what makes
 * a pill behave like one object — backspace at its edge removes the whole pill
 * instead of shaving a letter off its label, and the selection can never land
 * inside it. Hand-rolling that on a `contenteditable` means hand-writing
 * selection logic, and doing it correctly THROUGH an IME (this product's primary
 * input is Chinese) is where hand-rolled editors usually break.
 *
 * Refused: `StarterKit`. The composer's document is "one run of text plus some
 * atoms" — no headings, lists, marks or history-of-rich-marks — so the three
 * node specs it actually needs are declared here rather than pulled in behind a
 * schema nobody uses.
 */
import { Node, mergeAttributes } from '@tiptap/core'

import { MENTION_NODE_NAME } from './composer-document'

export const ComposerDocument = Node.create({
  name: 'doc',
  topNode: true,
  content: 'block+',
})

export const ComposerParagraph = Node.create({
  name: 'paragraph',
  group: 'block',
  content: 'inline*',
  parseHTML() {
    return [{ tag: 'p' }]
  },
  renderHTML({ HTMLAttributes }) {
    return ['p', mergeAttributes(HTMLAttributes), 0]
  },
})

export const ComposerText = Node.create({
  name: 'text',
  group: 'inline',
})

/**
 * One treatment for all five kinds, not one hue each.
 *
 * F4's 「输入框内联彩色 pill」 asks a pill to be visibly NOT typed text; it does
 * not ask the five kinds to be five colours, and colouring them that way would
 * break `FRONTEND_UI_SPEC.md` §2.2: colour encodes severity (good / attention /
 * failed / in progress) and never category, with the test being that a
 * desaturated screenshot must lose no information. Five hues for five kinds
 * fails that test outright.
 *
 * So the kind is carried the way that spec prescribes — by words: the menu
 * groups candidates under a kind heading at the moment of picking, the label
 * itself is distinctive (`plan` vs `plan.outline` vs `GRAPH.md`), and the pill
 * carries `kind · ref` as its hover title for the one case the label leaves
 * ambiguous (a file and a phase that happen to share a name).
 *
 * The fill is the sanctioned "this is primary" treatment for a surface that
 * bears text: a `bg-primary/10` wash under plain `text-foreground`. `--primary`
 * itself never becomes the letter colour — it measures 1.78:1 against `--card`,
 * the one token in the set that is unreadable as text (§2.2, and a test scans
 * for it).
 */
export const MENTION_PILL_CLASS =
  'mx-px inline-flex items-baseline rounded-sm border border-primary/30 bg-primary/10 px-1 align-baseline text-[0.95em] leading-tight text-foreground'

/**
 * A picked object, sitting inline in the sentence.
 *
 * Rendered as plain DOM rather than a React NodeView: the pill shows a label and
 * never changes after it is inserted, so a React reconciler inside ProseMirror
 * would buy nothing and cost a second update path over the same node.
 *
 * Refused `@tiptap/extension-mention`: its attributes are `(id, label)`, and
 * COPILOT_ASSIST-8 needs three — `kind` decides how `ref` is read, so folding
 * them into one `id` string would re-introduce the parsing the decision rejected.
 */
export const MentionPill = Node.create({
  name: MENTION_NODE_NAME,
  group: 'inline',
  inline: true,
  atom: true,
  selectable: true,
  draggable: false,

  addAttributes() {
    return {
      kind: { default: null },
      ref: { default: null },
      label: { default: null },
    }
  },

  parseHTML() {
    return [{ tag: 'span[data-mention-ref]' }]
  },

  renderHTML({ node, HTMLAttributes }) {
    const kind = String(node.attrs.kind ?? '')
    const ref = String(node.attrs.ref ?? '')
    return [
      'span',
      mergeAttributes(HTMLAttributes, {
        'data-mention-kind': kind,
        'data-mention-ref': ref,
        // The label is what the user picked BY; the ref is what was picked.
        // They differ for a phase inside a subgraph, and two objects of
        // different kinds can share a label — hover says which one this is.
        title: `${kind} · ${ref}`,
        class: MENTION_PILL_CLASS,
      }),
      `@${String(node.attrs.label ?? '')}`,
    ]
  },

  // What a copy-paste out of the composer carries: the same `@label` the sent
  // message carries, so what the user pastes elsewhere matches what was sent.
  renderText({ node }) {
    return `@${String(node.attrs.label ?? '')}`
  },
})
