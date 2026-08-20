import { PlayCircle } from 'lucide-react'
import type { CallbackEvent } from '../../api/types'
import { eventTimeLabel } from '../../utils/trace'

/**
 * Where a paused run picked up again.
 *
 * A resume is not a step — no engine work happened in it, exactly like the
 * outcome row at the other end. It is a SEAM: the run stopped, a person
 * answered, and the same run continued minutes or hours later. Rendering it as
 * an ordinary step left it falling through to a raw JSON payload, so the only
 * visible trace of the pause was a jump in the timestamps — which is how one
 * run's two time clusters came to be read as two runs bleeding into each other
 * (ledger T12: the stream layer was already proven clean).
 *
 * It therefore says the three things that make the jump legible: that this is
 * a resume, where it picked up, and what the person answered.
 */
export function TraceResumeSeam({ event }: { event: CallbackEvent }) {
  const phase = typeof event.resumed_from_phase === 'string' && event.resumed_from_phase !== ''
    ? event.resumed_from_phase
    : typeof event.phase_name === 'string' ? event.phase_name : null
  const answer = typeof event.human_input === 'string' ? event.human_input : ''
  const timeLabel = eventTimeLabel(event)

  return (
    <div data-trace-resume-seam={phase ?? ''} className="my-2 flex items-center gap-2">
      <span className="h-px flex-1 bg-border" />
      <span className="flex min-w-0 items-center gap-1.5 rounded-full border border-border bg-muted/40 px-2.5 py-0.5 text-[11px] text-muted-foreground">
        <PlayCircle className="h-3.5 w-3.5 shrink-0" />
        <span className="font-medium text-foreground">Resumed</span>
        {phase ? <span className="font-mono">{phase}</span> : null}
        {answer ? (
          <span className="truncate" title={answer}>answered: {answer}</span>
        ) : null}
        {timeLabel ? <span className="font-mono text-muted-foreground/80">{timeLabel}</span> : null}
      </span>
      <span className="h-px flex-1 bg-border" />
    </div>
  )
}
