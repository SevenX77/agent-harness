import { useState } from "react"
import useSWR from "swr"
import { ListChecks, Loader2, Plus, Sparkles, Trash2 } from "lucide-react"
import { createTestInput, deleteTestInput, fetcher } from "@/api/client"
import type { JsonObject, TestInputMetadata } from "@/api/types"
import { useBatchRun } from "@/hooks/useBatchRun"
import { errorMessage, isJsonObject } from "@/utils/errors"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { SectionHeading } from "./_shared/SectionHeading"

type PrepareResult =
  | { ok: true; name: string; content: JsonObject }
  | { ok: false; error: string }

/**
 * Pure client-side validation for the create form, mirroring the backend's
 * contract (non-empty name + JSON object content). Kept exported and pure so it
 * is unit-testable without `@testing-library/react`; the interactive flow is
 * covered by the Playwright e2e that drives the live panel.
 */
export function prepareTestInputCreate(name: string, contentText: string): PrepareResult {
  const trimmed = name.trim()
  if (!trimmed) {
    return { ok: false, error: "Name is required" }
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(contentText)
  } catch {
    return { ok: false, error: "Content must be valid JSON" }
  }
  if (!isJsonObject(parsed)) {
    return { ok: false, error: "Content must be a JSON object" }
  }
  return { ok: true, name: trimmed, content: parsed }
}

interface NamingSequenceItem {
  id: string
  name: string
}

export interface NamingSequenceGroup {
  /** Shared textual prefix, e.g. "chapter". */
  prefix: string
  /** Ids of the matched inputs, ordered by their numeric suffix. */
  ids: string[]
  /** Human label for the suggestion, e.g. "chapter1–3". */
  label: string
}

const NAMING_SEQUENCE_PATTERN = /^(.*?)(\d+)$/

/**
 * C10: detect a numeric naming sequence across `items[].name` — a shared
 * non-empty prefix followed by an incrementing integer suffix (chapter1 /
 * chapter2 / chapter3, ep1 / ep2 …). Returns the largest such group with at
 * least two members so the UI can suggest running it as a batch.
 *
 * Pure and exported so it is unit-testable under SSR (no `@testing-library`);
 * the click-to-batch flow is covered by the panel e2e.
 */
export function detectNamingSequence(items: readonly NamingSequenceItem[]): NamingSequenceGroup | null {
  const groups = new Map<string, { id: string; suffix: number }[]>()
  for (const item of items) {
    const match = NAMING_SEQUENCE_PATTERN.exec(item.name.trim())
    if (!match) {
      continue
    }
    const prefix = match[1]
    if (!prefix) {
      continue
    }
    const members = groups.get(prefix) ?? []
    members.push({ id: item.id, suffix: Number.parseInt(match[2], 10) })
    groups.set(prefix, members)
  }

  let best: NamingSequenceGroup | null = null
  for (const [prefix, members] of groups) {
    if (members.length < 2) {
      continue
    }
    const ordered = [...members].sort((a, b) => a.suffix - b.suffix)
    if (best && ordered.length <= best.ids.length) {
      continue
    }
    const first = ordered[0].suffix
    const last = ordered[ordered.length - 1].suffix
    best = {
      prefix,
      ids: ordered.map((member) => member.id),
      label: `${prefix}${first}–${last}`,
    }
  }
  return best
}

const EMPTY_CONTENT = "{\n  \n}"

interface TestInputsSectionProps {
  skillId: string
  workspaceRoot?: string | null
  // F4: which saved input feeds Predict/Run (null = empty payload).
  selectedId?: string | null
  onSelect?: (id: string | null) => void
}

export function TestInputsSection({
  skillId,
  workspaceRoot = null,
  selectedId = null,
  onSelect,
}: TestInputsSectionProps) {
  const { data, mutate } = useSWR<TestInputMetadata[]>(
    `/skills/${skillId}/test_inputs`,
    fetcher,
  )
  const [name, setName] = useState("")
  const [content, setContent] = useState(EMPTY_CONTENT)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const items = data ?? []
  // F6: batch run shares the same test_inputs SWR key, so the list is deduped.
  const batch = useBatchRun(skillId)

  // C10: when inputs form a naming sequence (chapter1/2/3), suggest running the
  // whole group as a batch. Hide the suggestion once the group is already fully
  // selected so it doesn't compete with the manual "Run N as batch" action.
  const sequence = detectNamingSequence(items)
  const isSequenceFullySelected =
    sequence !== null && sequence.ids.every((id) => batch.selectedInputIds.includes(id))
  const sequenceSuggestion = sequence && !isSequenceFullySelected ? sequence : null

  // Selecting the whole group + running happens atomically inside runBatch so we
  // don't race the async selection setState.
  const handleRunSequence = (group: NamingSequenceGroup) => {
    void batch.runBatch(group.ids)
  }

  const handleCreate = async () => {
    const prepared = prepareTestInputCreate(name, content)
    if (!prepared.ok) {
      setError(prepared.error)
      return
    }
    setError(null)
    setBusy(true)
    try {
      await createTestInput(skillId, prepared.name, prepared.content, { workspaceRoot })
      setName("")
      setContent(EMPTY_CONTENT)
      await mutate()
    } catch (err) {
      // Surface the backend's typed reason "就近" (e.g. duplicate name) rather
      // than a generic failure.
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async (id: string) => {
    setError(null)
    try {
      await deleteTestInput(skillId, id, { workspaceRoot })
      if (selectedId === id) {
        onSelect?.(null)
      }
      await mutate()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <section className="space-y-2">
      <SectionHeading label="Test Inputs" />
      <div className="space-y-1">
        {items.length === 0 ? (
          <p className="px-2 text-[11px] text-muted-foreground">No saved test inputs.</p>
        ) : (
          items.map((item) => {
            const isSelected = selectedId === item.id
            return (
              <div
                key={item.id}
                className={`flex items-center gap-2 rounded-md border px-2 py-1 ${
                  isSelected
                    ? "border-primary bg-accent"
                    : "border-border bg-background"
                }`}
              >
                <input
                  type="checkbox"
                  // F6: select inputs to run together as a batch.
                  checked={batch.selectedInputIds.includes(item.id)}
                  onChange={() => batch.toggleInput(item.id)}
                  aria-label={`Select test input ${item.id} for batch`}
                  className="size-3.5 shrink-0 rounded border-border"
                />
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      // F4: select this input as the Predict/Run payload (toggle off
                      // to fall back to empty).
                      onClick={() => onSelect?.(isSelected ? null : item.id)}
                      aria-pressed={isSelected}
                      aria-label={`Select test input ${item.id}`}
                      className="min-w-0 flex-1 truncate text-left text-xs text-foreground"
                    >
                      {item.name}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>{item.content_preview}</TooltipContent>
                </Tooltip>
                <button
                  type="button"
                  onClick={() => void handleDelete(item.id)}
                  aria-label={`Delete test input ${item.id}`}
                  className="text-muted-foreground transition-colors hover:text-destructive"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            )
          })
        )}
      </div>

      {sequenceSuggestion ? (
        <button
          type="button"
          // C10: one click selects the whole detected naming sequence and runs
          // it as a batch, sparing the user from ticking each input.
          onClick={() => handleRunSequence(sequenceSuggestion)}
          disabled={batch.batchRunning}
          aria-label={`Run ${sequenceSuggestion.label} as batch`}
          className="flex w-full items-center gap-1 rounded-md border border-dashed border-primary/50 bg-accent/40 px-2 py-1 text-left text-[11px] text-primary transition-opacity hover:opacity-80 disabled:opacity-50"
        >
          <Sparkles className="size-3.5 shrink-0" />
          <span className="truncate">
            Run {sequenceSuggestion.label} ({sequenceSuggestion.ids.length}) as batch
          </span>
        </button>
      ) : null}

      {batch.selectedInputIds.length > 0 || batch.batchStatus ? (
        <div className="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1 text-xs">
          <button
            type="button"
            onClick={() => void batch.runBatch()}
            disabled={batch.batchRunning || batch.selectedInputIds.length === 0}
            className="flex items-center gap-1 rounded-md bg-foreground px-2 py-0.5 font-medium text-background transition-opacity hover:opacity-80 disabled:opacity-50"
          >
            {batch.batchRunning ? <Loader2 className="size-3.5 animate-spin" /> : <ListChecks className="size-3.5" />}
            Run {batch.selectedInputIds.length} as batch
          </button>
          {batch.batchStatus ? (
            <span className="text-muted-foreground">
              {batch.batchStatus.completed}/{batch.batchStatus.total} · {batch.batchStatus.status}
            </span>
          ) : null}
          {batch.batchError ? <span className="text-destructive">{batch.batchError}</span> : null}
        </div>
      ) : null}

      <div className="space-y-2 rounded-md border border-border bg-background p-2">
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Name (e.g. happy-path)"
          aria-label="New test input name"
          className="w-full rounded-md border border-border bg-card px-2 py-1 text-xs"
        />
        <textarea
          value={content}
          onChange={(event) => setContent(event.target.value)}
          aria-label="New test input JSON"
          spellCheck={false}
          className="h-24 w-full resize-none rounded-md border border-border bg-card px-2 py-1 font-mono text-xs"
        />
        {error ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
            {error}
          </div>
        ) : null}
        <button
          type="button"
          onClick={() => void handleCreate()}
          disabled={busy}
          className="flex items-center gap-1 rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background transition-opacity hover:opacity-80 disabled:opacity-50"
        >
          <Plus className="size-3.5" />
          Save test input
        </button>
      </div>
    </section>
  )
}
