import { useState } from 'react'
import { Sparkles, X } from 'lucide-react'
import { toast } from 'sonner'
import {
  prepareCopilotJudgeContext,
  seedGoldenFromRun,
  type CopilotJudgeResponse,
} from '@/api/client'
import type { GoldenSeedPlan } from '@/api/types'
import { errorMessage } from '@/utils/errors'
import { Button } from '../ui/button'

interface SeedGoldenDeps {
  seed?: (skillId: string, runId: string, workspaceRoot?: string | null) => Promise<GoldenSeedPlan>
  judge?: (
    skillId: string,
    request: { runResultsRef: string; baselineRef: string },
  ) => Promise<CopilotJudgeResponse>
  runResultsRef?: string
  workspaceRoot?: string | null
}

function assertCopilotJudgeContextForRun(
  skillId: string,
  runResultsRef: string,
  judge: CopilotJudgeResponse,
): void {
  if (judge.diff_summary.run_results_ref !== runResultsRef) {
    throw new Error('Copilot Judge run_results_ref mismatch')
  }
  const skillPrefix = `${skillId}/`
  if (
    !judge.compare_result_ref.startsWith(skillPrefix)
    || !judge.judge_context_ref.startsWith(skillPrefix)
  ) {
    throw new Error('Copilot Judge refs must belong to the active skill')
  }
}

/**
 * F7 "无 golden 节点自动写 golden(有的不动)", asked per agent node.
 *
 * Which nodes lack a usable golden is a fact about files on disk, so the backend
 * answers it (`POST /golden/seed`) and this only relays the verdict: an absent
 * record, a missing case file and an empty/schema-mismatched one are the same
 * "no golden here" and all three seed from this run. Asking it here as
 * "does the skill have any baseline at all" was a run-level question the golden
 * model does not have (GOLDEN_EVAL-1: golden = one agent node's expected output).
 */
export async function seedGoldenForRun(
  skillId: string,
  runId: string,
  deps: SeedGoldenDeps = {},
): Promise<{ plan: GoldenSeedPlan; judge?: CopilotJudgeResponse }> {
  const seed = deps.seed ?? seedGoldenFromRun
  const judge = deps.judge ?? prepareCopilotJudgeContext
  const plan = await seed(skillId, runId, deps.workspaceRoot)

  if (deps.runResultsRef && plan.baseline_ref) {
    const judgeResult = await judge(skillId, {
      runResultsRef: deps.runResultsRef,
      baselineRef: plan.baseline_ref,
    })
    assertCopilotJudgeContextForRun(skillId, deps.runResultsRef, judgeResult)
    return { plan, judge: judgeResult }
  }
  return { plan }
}

/** What the bar says it did, in the user's terms rather than the plan's. */
export function seedOutcomeMessage(plan: GoldenSeedPlan): string {
  if (plan.baseline_locked) {
    return 'Golden 已锁定,未填充'
  }
  if (plan.seeded.length === 0) {
    return '每个节点都已有 golden,未改动'
  }
  const names = plan.seeded.map((target) => target.node_id).join('、')
  return `已用本次 run 的输出填充 ${plan.seeded.length} 个节点的 golden:${names}`
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
      const result = await seedGoldenForRun(skillId, runId, {
        workspaceRoot,
        runResultsRef: `${skillId}/runs/${runId}/result.json`,
      })
      if (result.judge) {
        onJudgePrepared?.(result.judge)
      }
      toast.success(seedOutcomeMessage(result.plan))
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
      <span className="min-w-0 flex-1 text-foreground">运行完成 — 用本次输出补上缺 golden 的节点?</span>
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
