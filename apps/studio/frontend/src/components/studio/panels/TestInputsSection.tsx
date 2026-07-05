import { useState } from "react"
import useSWR from "swr"
import { Loader2, Pencil, Plus, Trash2 } from "lucide-react"
import { createTestInput, deleteTestInput, fetcher } from "@/api/client"
import type { TestInputMetadata } from "@/api/types"
import { errorMessage } from "@/utils/errors"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { SectionHeading } from "./_shared/SectionHeading"

interface TestInputsSectionProps {
  skillId: string
  workspaceRoot?: string | null
  // F4: which saved input feeds Predict/Run (null = empty payload).
  selectedId?: string | null
  onSelect?: (id: string | null) => void
  /** Opens a test-input file in the editor ("New file" + per-row edit, P5). */
  onFileOpen?: (path: string) => void
}

export function TestInputsSection({
  skillId,
  workspaceRoot = null,
  selectedId = null,
  onSelect,
  onFileOpen,
}: TestInputsSectionProps) {
  const { data, mutate } = useSWR<TestInputMetadata[]>(
    `/skills/${skillId}/test_inputs`,
    fetcher,
  )
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const items = data ?? []

  // PM 2026-07-02 r2: no inline JSON form in the narrow panel — "New file"
  // creates an empty input in .workspace/import_files and opens it in the
  // editor; complex inputs come in via the input config dialog import.
  const handleNewFile = async () => {
    setError(null)
    setBusy(true)
    const existing = new Set(items.map((item) => item.id))
    let name = "input-1"
    for (let i = 1; existing.has(name); i += 1) {
      name = `input-${i}`
    }
    try {
      await createTestInput(skillId, name, {}, { workspaceRoot })
      await mutate()
      onFileOpen?.(`.workspace/import_files/${name}.json`)
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
                className={cn(
                  "flex items-center gap-2 rounded-md px-2 py-1 transition-colors",
                  isSelected
                    ? "bg-accent font-medium text-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
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
                {onFileOpen ? (
                  <button
                    type="button"
                    // P5: open this test input in the editor (next to delete).
                    onClick={() => onFileOpen(`.workspace/import_files/${item.id}.json`)}
                    aria-label={`Edit test input ${item.id}`}
                    className="text-muted-foreground transition-colors hover:text-foreground"
                  >
                    <Pencil className="size-3.5" />
                  </button>
                ) : null}
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

      {error ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
          {error}
        </div>
      ) : null}
      {/* PM 2026-07-03 #4: not a solid (near-black in dark) button — a ghost
          list row matching the test-input item rows above (transparent, hover
          lit), so "New file" aligns with the panel's existing list style. */}
      <button
        type="button"
        onClick={() => void handleNewFile()}
        disabled={busy}
        aria-label="New test input file"
        className={cn(
          "flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-xs transition-colors",
          "text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50",
        )}
      >
        {busy ? <Loader2 className="size-3.5 shrink-0 animate-spin" /> : <Plus className="size-3.5 shrink-0" />}
        New file
      </button>
      <p className="text-[11px] text-muted-foreground">
        Selected input feeds Predict and Run · New file opens in the editor
      </p>
    </section>
  )
}
