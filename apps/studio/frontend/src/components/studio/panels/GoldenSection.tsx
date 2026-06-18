import useSWR from "swr"
import { Lock } from "lucide-react"
import { fetcher } from "@/api/client"
import type { GoldenBaseline } from "@/api/types"
import { SectionHeading } from "./_shared/SectionHeading"

const relativeTime = (value: string): string => {
  const timestamp = new Date(value).getTime()
  if (Number.isNaN(timestamp)) {
    return value
  }
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

/**
 * F5 (input region): golden summary entry lives in the I/O panel — list the
 * skill's golden baselines (written via the analysis bar / promote). Opening the
 * golden file for edit needs a golden-content read endpoint (follow-on).
 */
export function GoldenSection({ skillId }: { skillId: string }) {
  const { data } = useSWR<GoldenBaseline[]>(`/skills/${skillId}/golden`, fetcher)
  const baselines = data ?? []

  return (
    <section className="space-y-2">
      <SectionHeading label="Golden" />
      {baselines.length === 0 ? (
        <p className="px-2 text-[11px] text-muted-foreground">No golden baselines yet.</p>
      ) : (
        <div className="space-y-1">
          {baselines.map((baseline) => (
            <div
              key={baseline.id}
              className="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1"
              title={baseline.content_path}
            >
              <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                {baseline.id}
                {baseline.source_run_id ? (
                  <span className="text-muted-foreground"> - source {baseline.source_run_id}</span>
                ) : null}
              </span>
              {baseline.locked ? <Lock className="size-3 text-muted-foreground" aria-label="locked" /> : null}
              <span className="text-[10px] text-muted-foreground">{relativeTime(baseline.created_at)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
