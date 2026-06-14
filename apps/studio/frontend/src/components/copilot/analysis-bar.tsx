import { useState } from 'react'
import { Sparkles, X } from 'lucide-react'
import { toast } from 'sonner'
import { listGoldenBaselines, saveGoldenBaseline } from '@/api/client'
import type { GoldenBaseline } from '@/api/types'
import { errorMessage } from '@/utils/errors'

interface AutoGoldenDeps {
  list?: (skillId: string) => Promise<GoldenBaseline[]>
  save?: (skillId: string, runId: string, lock?: boolean) => Promise<GoldenBaseline>
}

/**
 * F7 "无 golden 节点自动写 golden(有的不动)": with a run-level golden model,
 * this means — if the skill has no golden baseline yet, promote this run as the
 * baseline; if one already exists, leave it untouched. Pure + injectable so the
 * decision is unit-testable without the live API.
 */
export async function autoWriteGoldenIfAbsent(
  skillId: string,
  runId: string,
  deps: AutoGoldenDeps = {},
): Promise<{ written: boolean }> {
  const list = deps.list ?? listGoldenBaselines
  const save = deps.save ?? saveGoldenBaseline
  const existing = await list(skillId)
  if (existing.length > 0) {
    return { written: false }
  }
  await save(skillId, runId, false)
  return { written: true }
}

interface AnalysisBarProps {
  skillId: string
  runId: string
  onDismiss: () => void
}

/**
 * F7: a transient bar above the copilot input shown after a predict/run finishes,
 * offering to auto-write golden. Confirm or dismiss makes it disappear.
 */
export function AnalysisBar({ skillId, runId, onDismiss }: AnalysisBarProps) {
  const [busy, setBusy] = useState(false)

  const handleConfirm = async () => {
    setBusy(true)
    try {
      const result = await autoWriteGoldenIfAbsent(skillId, runId)
      toast.success(
        result.written ? 'Wrote golden baseline for this run' : 'Skill already has a golden baseline',
      )
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setBusy(false)
      onDismiss()
    }
  }

  return (
    <div className="mb-2 flex items-center gap-2 rounded-md border border-border bg-accent/50 px-3 py-1.5 text-xs">
      <Sparkles className="size-3.5 text-foreground" />
      <span className="min-w-0 flex-1 text-foreground">运行完成 — 自动写 golden(仅在尚无 golden 时)?</span>
      <button
        type="button"
        onClick={() => void handleConfirm()}
        disabled={busy}
        className="rounded-md bg-foreground px-2 py-0.5 font-medium text-background transition-opacity hover:opacity-80 disabled:opacity-50"
      >
        确认
      </button>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="忽略分析"
        className="text-muted-foreground transition-colors hover:text-foreground"
      >
        <X className="size-3.5" />
      </button>
    </div>
  )
}
