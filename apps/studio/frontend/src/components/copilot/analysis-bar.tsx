import { useState } from 'react'
import { useTranslation } from 'react-i18next'
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

/** What the bar did, in the user's terms rather than the plan's. */
export type SeedOutcome =
  | { kind: 'locked' }
  | { kind: 'nothingMissing' }
  | { kind: 'seeded'; nodeIds: string[] }

/**
 * Read the plan as an outcome.
 *
 * A descriptor, not a sentence: which language the reader gets is not
 * something a plan-reading function can know (设计源 i18n.md §3 Strategy C).
 * `seedOutcomeMessage` in the view turns this into words.
 */
export function seedOutcome(plan: GoldenSeedPlan): SeedOutcome {
  if (plan.baseline_locked) {
    return { kind: 'locked' }
  }
  if (plan.seeded.length === 0) {
    return { kind: 'nothingMissing' }
  }
  return { kind: 'seeded', nodeIds: plan.seeded.map((target) => target.node_id) }
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
  const { t } = useTranslation('copilot')
  const [busy, setBusy] = useState(false)

  const seedOutcomeMessage = (outcome: SeedOutcome): string => {
    if (outcome.kind === 'locked') return t('analysis.locked')
    if (outcome.kind === 'nothingMissing') return t('analysis.nothingMissing')
    return t('analysis.seeded', {
      count: outcome.nodeIds.length,
      nodes: outcome.nodeIds.join(t('analysis.nodeSeparator')),
    })
  }

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
      toast.success(seedOutcomeMessage(seedOutcome(result.plan)))
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
      <span className="min-w-0 flex-1 text-foreground">{t('analysis.prompt')}</span>
      <Button
        type="button"
        onClick={() => void handleConfirm()}
        disabled={busy}
        size="sm"
        variant="secondary"
        className="h-6 px-2 text-xs"
      >
        {t('analysis.confirm')}
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={onDismiss}
        aria-label={t('analysis.dismiss')}
        className="size-6 text-muted-foreground hover:text-foreground"
      >
        <X className="size-3.5" />
      </Button>
    </div>
  )
}
