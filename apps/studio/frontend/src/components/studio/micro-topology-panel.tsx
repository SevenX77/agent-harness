import { Brain, Hammer, ShieldCheck } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { CallbackEvent } from '../../api/types'
import { eventPhase } from '../../utils/trace'

interface MicroTopologyPanelProps {
  event: CallbackEvent | null
}

function jsonBlock(value: unknown) {
  if (value === undefined || value === null) {
    return 'null'
  }
  return JSON.stringify(value, null, 2)
}

export function MicroTopologyPanel({ event }: MicroTopologyPanelProps) {
  const metadata = event?.metadata
  const metrics = event?.metrics
  const sections: Array<[string, LucideIcon, unknown]> = [
    ['working_memory', Brain, metadata && typeof metadata === 'object' ? (metadata as Record<string, unknown>).working_memory : undefined],
    ['tool_calls', Hammer, metadata && typeof metadata === 'object' ? (metadata as Record<string, unknown>).tool_calls : undefined],
    ['validator', ShieldCheck, metrics && typeof metrics === 'object' ? (metrics as Record<string, unknown>).validator : undefined],
  ]

  return (
    <section className="rounded-md border border-border bg-card p-4">
      <h2 className="text-sm font-semibold text-foreground">Micro-topology</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        {event ? `${eventPhase(event)} / ${event.event_type}` : 'Select an LLM or trace event.'}
      </p>
      <div className="mt-4 grid gap-3">
        {sections.map(([label, Icon, value]) => (
          <div key={String(label)} className="rounded-md border border-border bg-background p-3">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <Icon className="size-3.5" />
              {String(label)}
            </div>
            <pre className="max-h-32 overflow-auto rounded-md bg-muted/40 p-2 text-xs text-foreground">
              {jsonBlock(value)}
            </pre>
          </div>
        ))}
      </div>
    </section>
  )
}
