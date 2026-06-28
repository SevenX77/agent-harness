import { useMemo, useState } from "react"
import useSWR from "swr"
import { ChevronDown, ChevronRight, Lock, Loader2, ShieldCheck, ShieldHalf } from "lucide-react"
import { fetcher, fetchGoldenContent, fetchGoldenTemplate, saveManualGolden } from "@/api/client"
import type {
  GoldenBaseline,
  GoldenCaseContent,
  JsonObject,
  SkillDetail,
} from "@/api/types"
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
            <GoldenBaselineRow
              key={baseline.id}
              skillId={skillId}
              baseline={baseline}
              onSaved={() => {
                void mutateBaselines()
              }}
            />
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
 * N4 atom #29: one golden baseline row. Read-only summary (id / source run / locked /
 * time); expanding it SWR-fetches the baseline's stored content
 * (GET /golden/{id}/content) so each per-node case's `expected_output` opens in an
 * editable JSON view. Saving an edit reuses the existing manual-golden write path
 * (saveManualGolden -> POST /golden/manual/plan -> Rust native-fs, D12) — no new write
 * endpoint.
 */
function GoldenBaselineRow({
  skillId,
  baseline,
  onSaved,
}: {
  skillId: string
  baseline: GoldenBaseline
  onSaved: () => void
}) {
  const [open, setOpen] = useState(false)
  // Only fetch content once the row is expanded (conditional SWR key).
  const { data: content, error } = useSWR(
    open ? `/skills/${skillId}/golden/${baseline.id}/content` : null,
    () => fetchGoldenContent(skillId, baseline.id),
  )
  const cases = content?.cases ?? []

  return (
    <div className="rounded-md border border-border bg-background">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 px-2 py-1 text-left"
        aria-expanded={open}
        title={baseline.content_path}
      >
        {open ? (
          <ChevronDown className="size-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
        )}
        <span className="min-w-0 flex-1 truncate text-xs text-foreground">
          {baseline.id}
          {baseline.source_run_id ? (
            <span className="text-muted-foreground"> - source {baseline.source_run_id}</span>
          ) : null}
        </span>
        {baseline.locked ? <Lock className="size-3 text-muted-foreground" aria-label="locked" /> : null}
        <span className="text-[10px] text-muted-foreground">{relativeTime(baseline.created_at)}</span>
      </button>
      {open ? (
        <div className="space-y-1.5 border-t border-border px-2 py-1.5">
          {error ? (
            <p className="text-[11px] text-destructive">
              {error instanceof Error ? error.message : "Failed to load golden content"}
            </p>
          ) : content === undefined ? (
            <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <Loader2 className="size-3 animate-spin" /> Loading content...
            </p>
          ) : cases.length === 0 ? (
            <p className="text-[11px] text-muted-foreground">No node cases in this baseline.</p>
          ) : (
            cases.map((goldenCase) => (
              <GoldenCaseEditor
                key={goldenCase.case_id}
                skillId={skillId}
                goldenCase={goldenCase}
                onSaved={onSaved}
              />
            ))
          )}
        </div>
      ) : null}
    </div>
  )
}

/**
 * Edit one golden case's expected_output. The JSON is seeded from the backend
 * GoldenCaseContent.expected_output (atom #29 read), hand-edited, then saved through the
 * existing manual-golden write (saveManualGolden, keyed by node_id) — the same Rust
 * native-fs sole writer the template-fill flow uses (D12). No new write path.
 */
export function GoldenCaseEditor({
  skillId,
  goldenCase,
  onSaved,
}: {
  skillId: string
  goldenCase: GoldenCaseContent
  onSaved: () => void
}) {
  const [draft, setDraft] = useState(() => JSON.stringify(goldenCase.expected_output, null, 2))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSave = async () => {
    let parsed: JsonObject
    try {
      parsed = JSON.parse(draft) as JsonObject
    } catch {
      setError("Expected output is not valid JSON")
      return
    }
    setBusy(true)
    setError(null)
    try {
      await saveManualGolden(skillId, goldenCase.node_id, parsed)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save golden")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-md border border-border bg-card px-2 py-1.5">
      <div className="flex items-center gap-1.5 text-xs text-foreground">
        <ShieldCheck className="size-3 shrink-0 text-emerald-600 dark:text-emerald-400" />
        <span className="truncate">{goldenCase.node_id}</span>
      </div>
      <Textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        spellCheck={false}
        className="mt-1.5 min-h-[120px] font-mono text-[11px]"
        aria-label={`Golden expected output for ${goldenCase.node_id}`}
      />
      <div className="mt-1.5 flex items-center justify-end gap-2">
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
      {error ? <p className="mt-1 text-[11px] text-destructive">{error}</p> : null}
    </div>
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
