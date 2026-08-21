import type { ComponentProps } from 'react'
import i18n from '@/i18n'
import { NODE_CAPSULE_BASE } from './node-card'
import type { SkillNodeStatus } from './types'

// The run-status capsule (decision 2026-08-13 D8): ONE definition of how a
// node status looks, consumed wherever a canvas card shows one. The status
// VALUES come from run-status-projection (D7) — this is only their clothes.
//
// The mark is a LAMP DOT, not a glyph: canvas design F3 ② specifies 小圆点灯,
// and the dot it names is the one Settings already uses for a live route
// (`roleRouteStatusLightClass` in settings/llm-roles/role-route-status.tsx) —
// same size, same ring, same pulse while working. A per-status icon set was
// drift: six glyphs to learn where one dot's colour already says it, and the
// two states a reader most needs to tell apart at a glance (running vs
// success) differed by icon SHAPE, which is the slowest difference to read on
// a zoomed-out board.
//
// The capsule's WORDING is not here. A status is a fact about the run; the
// noun a reader sees for it belongs to whichever language they picked, so it
// comes from `nodeStatusLabel` below and this table holds only clothes.
export const STATUS_STYLE: Record<SkillNodeStatus, { className: string; lampClassName: string }> = {
  idle: {
    className: 'border-border bg-card text-muted-foreground',
    lampClassName: 'bg-muted-foreground/50 ring-border',
  },
  running: {
    className: 'border-primary bg-primary/10 text-link',
    lampClassName: 'animate-pulse bg-primary ring-primary/30',
  },
  success: {
    className: 'border-success-border/60 bg-success/10 text-success',
    lampClassName: 'bg-success ring-success-border',
  },
  error: {
    className: 'border-destructive/50 bg-destructive/10 text-destructive',
    lampClassName: 'bg-destructive ring-destructive-border',
  },
  paused: {
    className: 'border-warning-border/60 bg-warning/10 text-warning',
    lampClassName: 'bg-warning ring-warning-border',
  },
  breakpoint: {
    className: 'border-primary/45 bg-primary/10 text-link',
    lampClassName: 'bg-primary ring-primary/30',
  },
}

// The word for a node's run status, in the reader's language.
//
// English says "Failed", not "Error": the label sits in the same row as the
// run's own vocabulary (idle / running / success / failed), and a node that
// failed is reporting its outcome, not naming an exception class.
export function nodeStatusLabel(status: SkillNodeStatus): string {
  return i18n.t(`status.${status}`, { ns: 'canvas' })
}

// Extra props (ref included — React 19 passes it as a prop) spread onto the
// span so a Radix `asChild` trigger can adopt the capsule as its element.
export function StatusCapsule({
  status,
  ...spanProps
}: { status: SkillNodeStatus } & ComponentProps<'span'>) {
  const style = STATUS_STYLE[status]
  return (
    <span {...spanProps} className={[NODE_CAPSULE_BASE, style.className].join(' ')}>
      <span
        aria-hidden
        className={['inline-flex size-1.5 shrink-0 rounded-full ring-1', style.lampClassName].join(' ')}
      />
      {nodeStatusLabel(status)}
    </span>
  )
}
