/** The copilot composer: a line of text that can hold picked objects.
 *
 * Design: `copilot-assist/mvp1-alignment.md` F4 ① ② + decision COPILOT_ASSIST-10.
 *
 * This component owns three things and nothing else: the editor document, which
 * row of the `@` menu the keyboard is on, and turning a pick into a pill. What a
 * pill means on the wire lives in `composer-document.ts`; what the menu may
 * offer lives in `mention-candidates.ts`.
 */
import { Extension, type Editor } from '@tiptap/core'
import { EditorContent, useEditor } from '@tiptap/react'
import { Plugin } from '@tiptap/pm/state'
import Suggestion from '@tiptap/suggestion'
import { forwardRef, useCallback, useImperativeHandle, useMemo, useRef, useState } from 'react'

import { isComposerSendKey } from './composer-keys'
import type { ComposerValue } from './composer-document'
import { MENTION_NODE_NAME, composerValueFromDoc } from './composer-document'
import { MentionMenu } from './MentionMenu'
import type { MentionCandidate, MentionGroup } from './mention-candidates'
import { filterMentionCandidates, flattenMentionGroups } from './mention-candidates'
import {
  ComposerDocument,
  ComposerParagraph,
  ComposerText,
  MentionPill,
} from './mention-node'

export interface MentionComposerHandle {
  clear(): void
  focus(): void
  /** Replace the whole document with prepared text — judge drafts, templates. */
  setText(text: string): void
}

export interface MentionComposerProps {
  /** Everything this workspace can name right now. */
  candidates: readonly MentionCandidate[]
  placeholder: string
  onChange: (value: ComposerValue) => void
  onSend: () => void
}

interface MenuAnchor {
  top: number
  bottom: number
  left: number
}

/**
 * Plugin order, and why each number is what it is.
 *
 * A key press is offered to plugins highest-priority first, and exactly one of
 * these three must claim Enter depending on what is on screen:
 *   * the `@` menu, when it is open — Enter picks a row;
 *   * send, otherwise;
 *   * tiptap's own base keymap last, which is what makes Shift-Enter split.
 */
const SUGGESTION_PRIORITY = 200
const SEND_PRIORITY = 150

/** Prepared drafts arrive as text; each line becomes its own paragraph. */
const LINE_BREAK = '\n'

export const MentionComposer = forwardRef<MentionComposerHandle, MentionComposerProps>(
  function MentionComposer({ candidates, placeholder, onChange, onSend }, ref) {
    // The extensions are built once — rebuilding them would tear down and
    // recreate the editor, losing the caret and any in-flight IME composition.
    // Everything that changes between renders is read through a ref instead.
    const candidatesRef = useRef(candidates)
    candidatesRef.current = candidates
    const onChangeRef = useRef(onChange)
    onChangeRef.current = onChange
    const onSendRef = useRef(onSend)
    onSendRef.current = onSend

    const flatRef = useRef<MentionCandidate[]>([])
    const commandRef = useRef<((candidate: MentionCandidate) => void) | null>(null)
    const activeIndexRef = useRef(0)

    const [menuGroups, setMenuGroups] = useState<MentionGroup[]>([])
    const [menuAnchor, setMenuAnchor] = useState<MenuAnchor | null>(null)
    const [activeIndex, setActiveIndexState] = useState(0)
    const [isEmpty, setIsEmpty] = useState(true)

    const setActiveIndex = useCallback((next: number) => {
      activeIndexRef.current = next
      setActiveIndexState(next)
    }, [])

    const closeMenu = useCallback(() => {
      flatRef.current = []
      commandRef.current = null
      setMenuGroups([])
      setMenuAnchor(null)
    }, [])

    const pick = useCallback((candidate: MentionCandidate | undefined) => {
      if (candidate) commandRef.current?.(candidate)
    }, [])

    const extensions = useMemo(() => {
      const mentionSuggestion = Extension.create({
        name: 'mentionSuggestion',
        priority: SUGGESTION_PRIORITY,
        addProseMirrorPlugins() {
          return [
            Suggestion<MentionCandidate, MentionCandidate>({
              editor: this.editor,
              char: '@',
              // A mention is one object, and its label never needs a space to be
              // typed; letting the query run past a space would make "@plan and"
              // one long non-matching query instead of a pill plus a sentence.
              allowSpaces: false,
              // The plugin awaits this to decide whether there is anything to
              // show; the menu itself re-derives from the query in `show`, so
              // there is no window where the rows and the query disagree.
              items: ({ query }) => flattenMentionGroups(filterMentionCandidates(candidatesRef.current, query)),
              command: ({ editor, range, props }) => {
                editor
                  .chain()
                  .focus()
                  .insertContentAt(range, [
                    {
                      type: MENTION_NODE_NAME,
                      attrs: { kind: props.kind, ref: props.ref, label: props.label },
                    },
                    // A trailing space so the next word is typed beside the pill
                    // rather than fighting the atom's right edge.
                    { type: 'text', text: ' ' },
                  ])
                  .run()
              },
              render: () => {
                // Everything shown is derived HERE from the query, not read
                // from what `items` last produced: the plugin calls `onStart`
                // before it has awaited `items`, so a menu fed from that side
                // would render the previous query's rows for a frame.
                const show = (props: {
                  query: string
                  command: (candidate: MentionCandidate) => void
                  clientRect?: (() => DOMRect | null) | null
                }) => {
                  const groups = filterMentionCandidates(candidatesRef.current, props.query)
                  const flat = flattenMentionGroups(groups)
                  flatRef.current = flat
                  commandRef.current = props.command
                  const rect = props.clientRect?.()
                  setMenuGroups(groups)
                  setMenuAnchor(
                    rect ? { top: rect.top, bottom: rect.bottom, left: rect.left } : null,
                  )
                  if (activeIndexRef.current >= flat.length) {
                    setActiveIndex(0)
                  }
                }
                return {
                  onStart: (props) => {
                    setActiveIndex(0)
                    show(props)
                  },
                  onUpdate: show,
                  onExit: closeMenu,
                  onKeyDown: ({ event }) => {
                    const items = flatRef.current
                    if (items.length === 0) return false
                    if (event.key === 'ArrowDown') {
                      setActiveIndex((activeIndexRef.current + 1) % items.length)
                      return true
                    }
                    if (event.key === 'ArrowUp') {
                      setActiveIndex(
                        (activeIndexRef.current - 1 + items.length) % items.length,
                      )
                      return true
                    }
                    if (event.key === 'Escape') {
                      closeMenu()
                      return true
                    }
                    if (event.key === 'Tab' || isComposerSendKey(event)) {
                      pick(items[activeIndexRef.current])
                      return true
                    }
                    return false
                  },
                }
              },
            }),
          ]
        },
      })

      const composerSend = Extension.create({
        name: 'composerSend',
        priority: SEND_PRIORITY,
        addKeyboardShortcuts() {
          // Without a base-keymap binding there is no way to start a second
          // line, and the design's composer is a message box, not a one-liner.
          return { 'Shift-Enter': () => this.editor.commands.splitBlock() }
        },
        addProseMirrorPlugins() {
          return [
            new Plugin({
              props: {
                handleKeyDown: (_view, event) => {
                  // Same rule the textarea used, IME guard included: a Chinese
                  // input method fires Enter to accept a candidate, and sending
                  // on that Enter would cut the word in half.
                  if (!isComposerSendKey(event)) return false
                  onSendRef.current()
                  return true
                },
              },
            }),
          ]
        },
      })

      return [
        ComposerDocument,
        ComposerParagraph,
        ComposerText,
        MentionPill,
        mentionSuggestion,
        composerSend,
      ]
    }, [closeMenu, pick, setActiveIndex])

    /**
     * Push the document out as the two things a turn carries.
     *
     * The editor is the single owner of the composer's content: the panel's
     * `draft` is a read-through projection of it, refreshed here. That is why
     * prepared drafts (judge context, templates) go in through `setText` rather
     * than by setting `draft` — setting the projection would leave the screen
     * showing the old document.
     */
    const publish = useCallback((instance: Editor) => {
      const value = composerValueFromDoc(instance.getJSON())
      setIsEmpty(value.text.trim().length === 0)
      onChangeRef.current(value)
    }, [])
    const publishRef = useRef(publish)
    publishRef.current = publish

    const editor = useEditor({
      extensions,
      onUpdate: ({ editor: instance }) => publishRef.current(instance),
      editorProps: {
        attributes: {
          class:
            'min-h-[60px] max-h-[160px] w-full overflow-y-auto whitespace-pre-wrap break-words text-sm leading-relaxed outline-none',
          'aria-label': placeholder,
          'data-copilot-composer': '',
        },
      },
    })

    useImperativeHandle(
      ref,
      () => ({
        clear: () => {
          editor?.commands.clearContent(true)
          setIsEmpty(true)
        },
        focus: () => editor?.commands.focus(),
        setText: (text: string) => {
          if (!editor) return
          // Built as an explicit document rather than handed to `setContent` as
          // a string: a string is parsed as HTML, so a draft containing `<`
          // would silently lose everything after it.
          editor.commands.setContent(
            {
              type: 'doc',
              content: text.split(LINE_BREAK).map((line) => ({
                type: 'paragraph',
                content: line ? [{ type: 'text', text: line }] : [],
              })),
            },
            { emitUpdate: false },
          )
          editor.commands.focus('end')
          publish(editor)
        },
      }),
      [editor, publish],
    )

    return (
      <div className="relative">
        <EditorContent editor={editor} />
        {isEmpty ? (
          <span
            aria-hidden
            className="pointer-events-none absolute left-0 top-0 select-none text-sm leading-relaxed text-muted-foreground"
          >
            {placeholder}
          </span>
        ) : null}
        <MentionMenu
          groups={menuGroups}
          activeIndex={activeIndex}
          anchor={menuAnchor}
          onPick={pick}
        />
      </div>
    )
  },
)
