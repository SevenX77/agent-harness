import { useEffect, useState } from 'react'
import type { NodeRuntime } from './types'

/**
 * How long a node's run segment lasted, written for a glance at a card.
 *
 * Precision drops as the number grows, because what the reader wants changes
 * with it: seconds matter on a 4s step, minutes on a 3-minute one, and nobody
 * reads the seconds digit on an hour-long phase. Borrowed shape: n8n's node
 * execution badge and GitHub Actions' step timers both step down this way.
 * Sub-second precision is deliberately NOT shown — the segment is bracketed by
 * two engine event timestamps, and presenting tenths would claim an accuracy
 * the event stream's own scheduling does not have.
 */
export function formatRunDuration(elapsedMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1000))
  if (totalSeconds < 60) return `${totalSeconds}s`
  const totalMinutes = Math.floor(totalSeconds / 60)
  if (totalMinutes < 60) return `${totalMinutes}m ${String(totalSeconds % 60).padStart(2, '0')}s`
  return `${Math.floor(totalMinutes / 60)}h ${String(totalMinutes % 60).padStart(2, '0')}m`
}

/**
 * The elapsed-time readout beside a node's status capsule.
 *
 * An open segment (`endedAtMs === null`) on a node the run still calls running
 * ticks once a second, LOCALLY: the second hand belongs to this one card, so
 * it must not travel through node data and force the whole board to rebuild
 * every tick.
 *
 * An open segment on a node that is NOT running renders nothing. That is the
 * crashed/cancelled run whose stream died mid-phase: the run record seals the
 * verdict but carries no end time, so the honest answer to "how long did it
 * take" is silence — never a clock that keeps running, and never a number
 * invented from when the reader happened to look.
 */
export function NodeRuntimeClock({ runtime, running }: { runtime: NodeRuntime; running: boolean }) {
  const isOpen = runtime.endedAtMs === null
  const isTicking = isOpen && running
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    if (!isTicking) return
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [isTicking])

  const endedAtMs = runtime.endedAtMs ?? (isTicking ? nowMs : null)
  if (endedAtMs === null) return null
  return (
    <span
      data-node-runtime={isTicking ? 'running' : 'settled'}
      className="text-[11px] tabular-nums text-muted-foreground"
    >
      {formatRunDuration(endedAtMs - runtime.startedAtMs)}
    </span>
  )
}
