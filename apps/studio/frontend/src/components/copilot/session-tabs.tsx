import { Plus, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
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
export function SessionTabs({ sessions, activeSessionId, onSwitch, onNew, onClose }: SessionTabsProps) {
  const tabs = sessionTabs(sessions, activeSessionId)
  const hasContent = sessions.some((session) => session.messages.length > 0)
  if (tabs.length <= 1 && !hasContent) {
    return null
  }

  return (
    <div className="flex items-center gap-1 border-b border-sidebar-border px-2 py-1.5">
      {/* R3: ScrollArea keeps the strip a single horizontal lane with the native
          scrollbar hidden (never a system scrollbar widget inside the bar). */}
      <ScrollArea className="min-w-0 flex-1 [&_[data-slot=scroll-area-scrollbar]]:hidden [&_[data-slot=scroll-area-viewport]>div]:!flex [&_[data-slot=scroll-area-viewport]>div]:items-center [&_[data-slot=scroll-area-viewport]>div]:gap-1">
        {tabs.map((tab) => (
          <span
            key={tab.id}
            data-copilot-session-tab={tab.id}
            className={cn(
              'group/tab inline-flex shrink-0 items-center rounded-md',
              tab.isActive ? 'bg-secondary' : '',
            )}
          >
            <Button
              type="button"
              size="sm"
              variant="ghost"
              aria-current={tab.isActive ? 'true' : undefined}
              title={tab.label}
              onClick={() => onSwitch(tab.id)}
              className={cn('max-w-[10rem] rounded-e-none pe-1', tab.isActive ? '' : 'text-muted-foreground')}
            >
              <span className="truncate">{tab.label}</span>
            </Button>
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
      </ScrollArea>
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        aria-label="New chat"
        title="New chat"
        onClick={onNew}
        className="shrink-0 text-muted-foreground"
      >
        <Plus />
      </Button>
    </div>
  )
}
