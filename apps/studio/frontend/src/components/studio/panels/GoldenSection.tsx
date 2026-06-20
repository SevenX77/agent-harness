import { useMemo, useState } from "react"
import useSWR from "swr"
import { Lock, Loader2, ShieldCheck, ShieldHalf } from "lucide-react"
import { fetcher, fetchGoldenTemplate, saveManualGolden } from "@/api/client"
import type { GoldenBaseline, JsonObject, SkillDetail } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { templatableAgentNodeIds } from "@/components/studio/node-golden"
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
 * F5 (input region): golden summary entry lives in the I/O panel — list the skill's
 * golden baselines, plus the N4 atom #33 create-path B template-fill flow: for an agent
 * node WITHOUT golden, generate a schema-valid empty template, hand-fill it, and save it
 * as a manual (run-less) golden so the canvas badge flips 🟢.
 */
export function GoldenSection({ skillId }: { skillId: string }) {
  const { data: baselines, mutate: mutateBaselines } = useSWR<GoldenBaseline[]>(
    `/skills/${skillId}/golden`,
    fetcher,
  )
  const { data: detail } = useSWR<SkillDetail>(`/skills/${skillId}`, fetcher)

  // Agent nodes without golden are the manual-template targets (logic/subgraph never get
  // golden, design g-c; 🟢 nodes already have golden so they're excluded).
  const templatableNodeIds = useMemo(
    () => templatableAgentNodeIds(detail?.graph_topology, baselines),
    [detail, baselines],
  )

  return (
    <section className="space-y-2">
      <SectionHeading label="Golden" />
      {(baselines ?? []).length === 0 ? (
        <p className="px-2 text-[11px] text-muted-foreground">No golden baselines yet.</p>
      ) : (
        <div className="space-y-1">
          {(baselines ?? []).map((baseline) => (
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

      {templatableNodeIds.length > 0 ? (
        <div className="space-y-1">
          <SectionHeading label="Fill golden by template" />
          {templatableNodeIds.map((nodeId) => (
            <GoldenTemplateRow
              key={nodeId}
              skillId={skillId}
              nodeId={nodeId}
              onSaved={() => {
                void mutateBaselines()
              }}
            />
          ))}
        </div>
      ) : null}
    </section>
  )
}

/**
 * One agent node's manual-template flow: Generate template -> edit JSON -> save golden.
 */
function GoldenTemplateRow({
  skillId,
  nodeId,
  onSaved,
}: {
  skillId: string
  nodeId: string
  onSaved: () => void
}) {
  const [draft, setDraft] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleGenerate = async () => {
    setBusy(true)
    setError(null)
    try {
      const template = await fetchGoldenTemplate(skillId, nodeId)
      setDraft(JSON.stringify(template.template, null, 2))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate template")
    } finally {
      setBusy(false)
    }
  }

  const handleSave = async () => {
    if (draft === null) return
    let parsed: JsonObject
    try {
      parsed = JSON.parse(draft) as JsonObject
    } catch {
      setError("Template is not valid JSON")
      return
    }
    setBusy(true)
    setError(null)
    try {
      await saveManualGolden(skillId, nodeId, parsed)
      setDraft(null)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save golden")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-md border border-border bg-card px-2 py-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5 truncate text-xs text-foreground">
          <ShieldHalf className="size-3 shrink-0 text-amber-600 dark:text-amber-400" />
          {nodeId}
        </span>
        {draft === null ? (
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy}
            onClick={() => {
              void handleGenerate()
            }}
          >
            {busy ? <Loader2 className="size-3.5 animate-spin" /> : null}
            Generate template
          </Button>
        ) : null}
      </div>
      {draft !== null ? (
        <div className="mt-1.5 space-y-1.5">
          <Textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            spellCheck={false}
            className="min-h-[120px] font-mono text-[11px]"
            aria-label={`Golden template for ${nodeId}`}
          />
          <div className="flex items-center justify-end gap-2">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => {
                setDraft(null)
                setError(null)
              }}
            >
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              variant="default"
              disabled={busy}
              onClick={() => {
                void handleSave()
              }}
            >
              {busy ? <Loader2 className="size-3.5 animate-spin" /> : <ShieldCheck className="size-3.5" />}
              Save golden
            </Button>
          </div>
        </div>
      ) : null}
      {error ? <p className="mt-1 text-[11px] text-destructive">{error}</p> : null}
    </div>
  )
}
