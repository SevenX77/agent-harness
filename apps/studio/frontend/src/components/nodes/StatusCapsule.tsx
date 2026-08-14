import type { ComponentProps } from 'react'
import { AlertTriangle, CheckCircle2, Circle, Pause, Radio, Workflow } from 'lucide-react'
import { NODE_CAPSULE_BASE } from './node-card'
import type { SkillNodeStatus } from './types'

// The run-status capsule (decision 2026-08-13 D8): ONE definition of how a
// node status looks, consumed wherever a canvas card shows one. The status
// VALUES come from run-status-projection (D7) — this is only their clothes.
export const STATUS_STYLE: Record<SkillNodeStatus, { label: string; className: string; icon: typeof Circle }> = {
  idle: {
    label: 'Idle',
    className: 'border-border bg-card text-muted-foreground',
    icon: Circle,
  },
  running: {
    label: 'Running',
    className: 'animate-pulse-primary border-primary bg-primary/10 text-link',
    icon: Radio,
  },
  success: {
    label: 'Success',
    className: 'border-success-border/60 bg-success/10 text-success',
    icon: CheckCircle2,
  },
  error: {
    label: 'Error',
    className: 'border-destructive/50 bg-destructive/10 text-destructive',
    icon: AlertTriangle,
  },
  paused: {
    label: 'Paused',
    className: 'border-warning-border/60 bg-warning/10 text-warning',
    icon: Pause,
  },
  breakpoint: {
    label: 'Breakpoint',
    className: 'border-primary/45 bg-primary/10 text-link',
    icon: Workflow,
  },
}

// Extra props (ref included — React 19 passes it as a prop) spread onto the
// span so a Radix `asChild` trigger can adopt the capsule as its element.
export function StatusCapsule({
  status,
  ...spanProps
}: { status: SkillNodeStatus } & ComponentProps<'span'>) {
  const style = STATUS_STYLE[status]
  const StatusIcon = style.icon
  return (
    <span {...spanProps} className={[NODE_CAPSULE_BASE, style.className].join(' ')}>
      <StatusIcon className="size-3" />
      {style.label}
    </span>
  )
}
