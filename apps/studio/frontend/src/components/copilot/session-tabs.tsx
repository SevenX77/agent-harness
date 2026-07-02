import React, { useEffect, useRef } from 'react'
import { Plus, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { CopilotSession } from '../../store/copilotStore'

/** A session reduced to what the tab bar needs to render + select (R17). */
export interface SessionTab {
  id: string
  label: string
  isActive: boolean
}

/**
 * Derive a short, human label for a session tab. Sessions have no title, so we
 * use the first user message (trimmed + first line) as the label, falling back
 * to a 1-based "Chat N" when the session has no user turn yet (e.g. a freshly
 * minted "+" chat). Keeps the bar readable without depending on backend titles.
 */
export function sessionTabLabel(session: CopilotSession, index: number): string {
  const firstUser = session.messages.find((message) => message.role === 'user')
  const raw = firstUser?.content.trim().split('\n', 1)[0]?.trim() ?? ''
  if (raw.length === 0) {
    return `Chat ${index + 1}`
  }
  return raw.length > 24 ? `${raw.slice(0, 24)}…` : raw
}

/**
 * Pure list→tabs mapping: the order is preserved from the store (chronological),
 * each tab carries a derived label and whether it is the active session. Kept
 * pure + exported so the selection logic is unit-testable without a DOM (R17).
 */
export function sessionTabs(
  sessions: CopilotSession[],
  activeSessionId: string | null,
): SessionTab[] {
  return sessions.map((session, index) => ({
    id: session.id,
    label: sessionTabLabel(session, index),
    isActive: session.id === activeSessionId,
  }))
}

/**
 * R5-B (F1): translate a dominant VERTICAL wheel gesture into horizontal strip
 * scroll. Returns whether the event was consumed (caller preventDefaults then).
 * Native horizontal gestures (trackpad pans, |deltaX| >= |deltaY|) and strips
 * without overflow are left to the browser. Pure + exported for unit tests.
 */
export function consumeHorizontalWheel(
  viewport: { scrollLeft: number; scrollWidth: number; clientWidth: number },
  deltaX: number,
  deltaY: number,
): boolean {
  if (viewport.scrollWidth <= viewport.clientWidth) {
    return false
  }
  if (Math.abs(deltaX) >= Math.abs(deltaY)) {
    return false
  }
  viewport.scrollLeft += deltaY
  return true
}

interface SessionTabsProps {
  sessions: CopilotSession[]
  activeSessionId: string | null
  onSwitch: (id: string) => void
  onNew: () => void
  onClose: (id: string) => void
}

/**
 * Compact, horizontally-scrollable session tab bar with a trailing "+" to start
 * a new chat (R17). Renders nothing until there is more than one session OR a
 * non-empty conversation — a single empty chat needs no switcher. Reuses the
 * shadcn Button; no bespoke UI.
 */
export function SessionTabs(props: SessionTabsProps) {
  const stripRef = useRef<HTMLDivElement | null>(null)

  // R5-B: vertical wheel over the strip scrolls it horizontally. Native wheel
  // listener (not React onWheel) because preventDefault needs passive:false.
  // No dep array: the viewport mounts/unmounts with the strip's own visibility
  // rule, so rebinding per render keeps the listener attached to the live node.
  useEffect(() => {
    const viewport = stripRef.current?.querySelector<HTMLElement>('[data-slot=scroll-area-viewport]')
    if (!viewport) {
      return
    }
    const onWheel = (event: WheelEvent) => {
      if (consumeHorizontalWheel(viewport, event.deltaX, event.deltaY)) {
        event.preventDefault()
      }
    }
    viewport.addEventListener('wheel', onWheel, { passive: false })
    return () => viewport.removeEventListener('wheel', onWheel)
  })

  return <SessionTabsView {...props} stripRef={stripRef} />
}

/** Hook-free presentational strip — kept separate so interaction tests can walk
 * the element tree by calling it directly (project has no testing-library). */
export function SessionTabsView({
  sessions,
  activeSessionId,
  onSwitch,
  onNew,
  onClose,
  stripRef,
}: SessionTabsProps & { stripRef?: React.Ref<HTMLDivElement> }) {
  const tabs = sessionTabs(sessions, activeSessionId)
  const hasContent = sessions.some((session) => session.messages.length > 0)
  if (tabs.length <= 1 && !hasContent) {
    return null
  }

  return (
    <div className="flex items-center gap-1 border-b border-sidebar-border px-2 py-1.5">
      {/* R3: ScrollArea keeps the strip a single horizontal lane (never a system
          scrollbar widget). R5-B: a THIN hover-only horizontal ScrollBar replaces
          the old fully-hidden one — overflow must be discoverable. */}
      <ScrollArea
        ref={stripRef}
        className="min-w-0 flex-1 [&_[data-slot=scroll-area-viewport]>div]:!flex [&_[data-slot=scroll-area-viewport]>div]:items-center [&_[data-slot=scroll-area-viewport]>div]:gap-1"
      >
        {tabs.map((tab) => (
          <span
            key={tab.id}
            data-copilot-session-tab={tab.id}
            className={cn(
              'group/tab inline-flex shrink-0 items-center rounded-md',
              tab.isActive ? 'bg-secondary' : '',
            )}
          >
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  aria-current={tab.isActive ? 'true' : undefined}
                  onClick={() => onSwitch(tab.id)}
                  className={cn('max-w-[10rem] rounded-e-none pe-1', tab.isActive ? '' : 'text-muted-foreground')}
                >
                  <span className="truncate">{tab.label}</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>{tab.label}</TooltipContent>
            </Tooltip>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              aria-label={`Close ${tab.label}`}
              onClick={() => onClose(tab.id)}
              className="size-6 rounded-s-none text-muted-foreground opacity-60 hover:text-foreground group-hover/tab:opacity-100"
            >
              <X className="size-3" />
            </Button>
          </span>
        ))}
        <ScrollBar
          orientation="horizontal"
          className="data-horizontal:h-1.5 data-horizontal:border-t-0"
        />
      </ScrollArea>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            aria-label="New chat"
            onClick={onNew}
            className="shrink-0 text-muted-foreground"
          >
            <Plus />
          </Button>
        </TooltipTrigger>
        <TooltipContent>New chat</TooltipContent>
      </Tooltip>
    </div>
  )
}
