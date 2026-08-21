import { AlertTriangle } from 'lucide-react'
import type { CompareTab } from '@/components/studio/run-compare'
import { useTraceCopy } from './trace-copy'

interface CompareCandidateTabsProps {
  tabs?: CompareTab[]
  activeCandidateId?: string | null
  onSelect?: (candidateId: string) => void
}

/**
 * The per-candidate strip for a node's Compare LLMs group: one tab per model
 * candidate, pointing the trace at that candidate's side-run.
 *
 * It is rendered by the trace REGION, not by TracePanel. Its precondition is
 * "a compare group exists" — a sentence with no live run in it — so mounting it
 * under the live branch made the group unreachable whenever the compare was
 * started off a run opened from history, which is precisely the case the base
 * run is allowed to be (ledger L2). Same rule as FocusedNodeActions:
 * FRONTEND_UI_SPEC §2.9b, the action is rendered by whoever its precondition
 * belongs to.
 *
 * A tab appears as soon as its side-run is spawned, before any of its events
 * arrive, so the reader can move between candidates while one is still empty.
 */
export function CompareCandidateTabs({ tabs, activeCandidateId = null, onSelect }: CompareCandidateTabsProps) {
  const t = useTraceCopy()
  if (!Array.isArray(tabs) || tabs.length === 0) {
    return null
  }
  return (
    <div
      role="tablist"
      aria-label={t('panel.candidates')}
      className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-border bg-card px-2 py-1.5"
    >
      {tabs.map((tab) => {
        const isActive = tab.candidateId === activeCandidateId
        return (
          <button
            key={tab.candidateId}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-label={tab.failed
              ? t('panel.candidateFailed', { name: tab.label })
              : t('panel.candidate', { name: tab.label })}
            onClick={() => onSelect?.(tab.candidateId)}
            className={[
              'flex items-center gap-1 whitespace-nowrap rounded-md border px-2 py-1 text-xs font-semibold transition-colors',
              isActive
                ? 'border-primary bg-primary/10 text-foreground'
                : 'border-border bg-card text-muted-foreground hover:bg-accent',
              tab.failed ? 'text-destructive' : '',
            ].join(' ')}
          >
            {tab.failed ? <AlertTriangle className="size-3" /> : null}
            {tab.running ? (
              <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-primary" />
            ) : null}
            <span className="max-w-[140px] truncate">{tab.label}</span>
          </button>
        )
      })}
    </div>
  )
}
