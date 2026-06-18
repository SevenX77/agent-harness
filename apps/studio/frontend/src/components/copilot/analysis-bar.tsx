import { useState } from 'react'
import { Sparkles, X } from 'lucide-react'
import { toast } from 'sonner'
import {
  listGoldenBaselines,
  prepareCopilotJudgeContext,
  saveGoldenBaseline,
  type CopilotJudgeResponse,
} from '@/api/client'
import type { GoldenBaseline } from '@/api/types'
import { errorMessage } from '@/utils/errors'
import { Button } from '../ui/button'

interface AutoGoldenDeps {
  list?: (skillId: string) => Promise<GoldenBaseline[]>
  save?: (
    skillId: string,
    runId: string,
    lock?: boolean,
    workspaceRoot?: string | null,
  ) => Promise<GoldenBaseline>
  judge?: (
    skillId: string,
    request: { runResultsRef: string; baselineRef: string },
  ) => Promise<CopilotJudgeResponse>
  runResultsRef?: string
  workspaceRoot?: string | null
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
): Promise<{ written: boolean; judge?: CopilotJudgeResponse }> {
  const list = deps.list ?? listGoldenBaselines
  const save = deps.save ?? saveGoldenBaseline
  const judge = deps.judge ?? prepareCopilotJudgeContext
  const existing = await list(skillId)
  let baseline = existing[0] ?? null
  let written = false
  if (existing.length > 0) {
    written = false
  } else {
    if (deps.workspaceRoot?.trim()) {
      baseline = await save(skillId, runId, false, deps.workspaceRoot)
    } else {
      baseline = await save(skillId, runId, false)
    }
    written = true
  }

  const baselineRef = baseline?.baseline_ref
  if (deps.runResultsRef && baselineRef) {
    return {
      written,
      judge: await judge(skillId, {
        runResultsRef: deps.runResultsRef,
        baselineRef,
      }),
    }
  }
  return { written }
}

interface AnalysisBarProps {
  skillId: string
  runId: string
  workspaceRoot?: string | null
  onJudgePrepared?: (refs: CopilotJudgeResponse) => void
  onDismiss: () => void
}

/**
 * F7: a transient bar above the copilot input shown after a predict/run finishes,
 * offering to auto-write golden. Confirm or dismiss makes it disappear.
 */
export function AnalysisBar({ skillId, runId, workspaceRoot, onJudgePrepared, onDismiss }: AnalysisBarProps) {
  const [busy, setBusy] = useState(false)

  const handleConfirm = async () => {
    setBusy(true)
    try {
      const result = await autoWriteGoldenIfAbsent(skillId, runId, {
        workspaceRoot,
        runResultsRef: `${skillId}/runs/${runId}/result.json`,
      })
      if (result.judge) {
        onJudgePrepared?.(result.judge)
      }
      toast.success(
        result.written ? 'Wrote golden baseline and prepared judge context' : 'Prepared judge context',
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
      <Button
        type="button"
        onClick={() => void handleConfirm()}
        disabled={busy}
        size="sm"
        variant="secondary"
        className="h-6 px-2 text-xs"
      >
        确认
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={onDismiss}
        aria-label="忽略分析"
        className="size-6 text-muted-foreground hover:text-foreground"
      >
        <X className="size-3.5" />
      </Button>
    </div>
  )
}
