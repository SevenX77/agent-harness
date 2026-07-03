import { useEffect, useState } from 'react'

export type PresenceState = 'open' | 'closed'

export interface AnimatedPresence {
  /** Whether the content should be in the tree (true through the exit animation). */
  mounted: boolean
  /** Drives `data-state` so CSS can pick the enter vs exit animation. */
  state: PresenceState
}

/**
 * Keeps content mounted across an exit animation, WITHOUT relying on the
 * `animationend` event — the copilot panel has its own inner animations
 * (shimmer, streaming) whose `animationend` bubbles up and would unmount the
 * panel mid-flight. Instead we hold the mount for a fixed `durationMs` that
 * matches the CSS exit animation, which is deterministic and bubbling-proof.
 *
 * - `open` flips true  → mount immediately; the enter animation plays.
 * - `open` flips false → keep mounted for `durationMs`, then unmount (exit plays).
 * - `durationMs <= 0`  → unmount synchronously (reduced-motion path).
 */
export function useAnimatedPresence(open: boolean, durationMs: number): AnimatedPresence {
  const [mounted, setMounted] = useState(open)

  useEffect(() => {
    if (open) {
      setMounted(true)
      return
    }
    if (durationMs <= 0) {
      setMounted(false)
      return
    }
    const timer = setTimeout(() => setMounted(false), durationMs)
    return () => clearTimeout(timer)
  }, [open, durationMs])

  return { mounted, state: open ? 'open' : 'closed' }
}
