import { AlertCircle, CheckCircle2, CirclePause, Loader2, XCircle, type LucideIcon } from 'lucide-react'
import type { RunStatus } from '../api/types'
import type { TraceRunOutcome } from './trace'

export interface RunStatusMark {
  icon: LucideIcon
  label: string
  tone: string
}

/**
 * How a run stands, as ONE icon — the single vocabulary two screens share.
 *
 * The trace strip and the run list must read the same way (decision 2026-08-09
 * D9: "状态图标徽章(与 D3 同一套)... 与 Trace 顶条同构,两屏读法一致"), and two
 * copies of a status table drift the moment one of them gains a status.
 *
 * The word survives in the label, which every caller puts on the element as its
 * accessible name and its tooltip, so nothing is lost to a screen reader or to
 * a user who hovers.
 *
 * Returns null for a status that is not known, so a caller renders nothing
 * rather than guessing.
 */
export function runStatusMark(
  status: RunStatus | TraceRunOutcome | null | undefined,
): RunStatusMark | null {
  switch (status) {
    case 'success':
      return { icon: CheckCircle2, label: 'Run succeeded', tone: 'text-success' }
    case 'interrupted':
    case 'paused':
      return { icon: CirclePause, label: 'Run paused', tone: 'text-warning' }
    case 'running':
      return { icon: Loader2, label: 'Run in progress', tone: 'animate-spin text-muted-foreground' }
    case 'cancelled':
      return { icon: XCircle, label: 'Run cancelled', tone: 'text-destructive' }
    case 'failed':
      return { icon: AlertCircle, label: 'Run failed', tone: 'text-destructive' }
    default:
      return null
  }
}
