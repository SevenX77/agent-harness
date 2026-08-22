/** The list that opens when the user types `@`.
 *
 * Design: `copilot-assist/mvp1-alignment.md` F4 ① + decision COPILOT_ASSIST-10 ③.
 *
 * Presentational only: it renders the groups it is handed and reports a pick.
 * Which row is active, and every key that moves it, belong to the editor — see
 * `MentionComposer`.
 *
 * Deliberately NOT the local `cmdk` Command wrapper, even though this is a
 * filtered command list: `Command` takes focus and runs its own filter, and both
 * are already owned here. Focus must stay in the editor or typing stops mid-word
 * (and an IME composition would be torn in half); the filter is
 * `filterMentionCandidates`, which the design pins to F4's kind order.
 */
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'

import { MENTION_PILL_CLASS } from './mention-node'
import type { MentionCandidate, MentionGroup } from './mention-candidates'

export interface MentionMenuProps {
  groups: readonly MentionGroup[]
  /** Index into the flattened groups — the row the keyboard is on. */
  activeIndex: number
  onPick: (candidate: MentionCandidate) => void
  /** Where the caret is, in viewport coordinates. */
  anchor: { top: number; bottom: number; left: number } | null
}

const MENU_WIDTH = 320
const MENU_MAX_HEIGHT = 288
const ANCHOR_GAP = 6

export function MentionMenu({ groups, activeIndex, onPick, anchor }: MentionMenuProps) {
  const { t } = useTranslation('copilot')
  const activeRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'nearest' })
  }, [activeIndex])

  if (!anchor || groups.length === 0) {
    return null
  }

  // Open upward when the caret sits low enough that a downward menu would run
  // off-screen — the composer lives at the BOTTOM of the panel, so upward is the
  // common case rather than the fallback.
  const opensDown = anchor.bottom + ANCHOR_GAP + MENU_MAX_HEIGHT <= window.innerHeight
  const style = {
    width: MENU_WIDTH,
    maxHeight: MENU_MAX_HEIGHT,
    left: Math.max(8, Math.min(anchor.left, window.innerWidth - MENU_WIDTH - 8)),
    ...(opensDown
      ? { top: anchor.bottom + ANCHOR_GAP }
      : { bottom: window.innerHeight - anchor.top + ANCHOR_GAP }),
  }

  let flatIndex = -1
  return (
    <div
      role="listbox"
      aria-label={t('composer.mentionMenu.label')}
      data-mention-menu=""
      className="fixed z-[var(--z-copilot)] overflow-y-auto rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
      style={style}
    >
      {groups.map((group) => (
        <div key={group.kind} role="group" aria-labelledby={`mention-group-${group.kind}`}>
          <div
            id={`mention-group-${group.kind}`}
            className="flex items-baseline justify-between px-2 py-1 text-[0.7rem] font-medium uppercase tracking-wide text-muted-foreground"
          >
            <span>{t(`composer.mentionMenu.kind.${group.kind}`)}</span>
            {/* A list that quietly stopped at eight would read as "it isn't
                here" (COPILOT_ASSIST-10 ③). Saying the number turns that into
                "keep typing". */}
            {group.hiddenCount > 0 ? (
              <span data-mention-hidden-count={group.hiddenCount}>
                {t('composer.mentionMenu.more', { count: group.hiddenCount })}
              </span>
            ) : null}
          </div>
          {group.items.map((item) => {
            flatIndex += 1
            const isActive = flatIndex === activeIndex
            return (
              <button
                key={`${item.kind}:${item.ref}`}
                ref={isActive ? activeRef : undefined}
                type="button"
                role="option"
                aria-selected={isActive}
                data-mention-option={`${item.kind}:${item.ref}`}
                // The editor keeps focus, so the row must not steal it on the
                // mousedown that precedes click — losing focus would close the
                // suggestion and drop the query.
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => onPick(item)}
                className={`flex w-full items-baseline gap-2 rounded-sm px-2 py-1 text-left text-sm ${
                  isActive ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50'
                }`}
              >
                <span className={MENTION_PILL_CLASS}>@{item.label}</span>
                {item.detail ? (
                  <span className="truncate text-xs text-muted-foreground">{item.detail}</span>
                ) : null}
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}
