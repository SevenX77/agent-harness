import { useState } from "react"
import useSWR from "swr"
import { ListChecks, Loader2, Plus, Trash2 } from "lucide-react"
import { createTestInput, deleteTestInput, fetcher } from "@/api/client"
import type { JsonObject, TestInputMetadata } from "@/api/types"
import { useBatchRun } from "@/hooks/useBatchRun"
import { errorMessage, isJsonObject } from "@/utils/errors"
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
                <button
                  type="button"
                  // F4: select this input as the Predict/Run payload (toggle off
                  // to fall back to empty).
                  onClick={() => onSelect?.(isSelected ? null : item.id)}
                  aria-pressed={isSelected}
                  aria-label={`Select test input ${item.id}`}
                  title={item.content_preview}
                  className="min-w-0 flex-1 truncate text-left text-xs text-foreground"
                >
                  {item.name}
                </button>
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
