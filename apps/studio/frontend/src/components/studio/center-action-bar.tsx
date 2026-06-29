import type { ReactNode } from "react"
import { Hammer, Play, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

export type SkillBuildStage =
  | "idle"
  | "compiling"
  | "compile-fail"
  | "compile-pass"
  | "predicting"
  | "predict-fail"
  | "predict-pass"
  | "running"
  | "run-fail"

interface CenterActionBarProps {
  stage: SkillBuildStage
  onCompile?: () => void
  onPredict?: () => void
  onRun?: () => void
}

interface ButtonDerivation {
  compileHighlight: boolean
  compileDisabled: boolean
  predictHighlight: boolean
  predictDisabled: boolean
  runHighlight: boolean
  runDisabled: boolean
}

// Visible UI copy stays English to match the Compile/Predict/Run buttons and the
// product's English surface. Shown when a gate keeps the button locked.
const PREDICT_LOCK_REASON = "Compile must pass first"
const RUN_LOCK_REASON = "Predict must pass first"

function deriveButtons(stage: SkillBuildStage): ButtonDerivation {
  if (stage === "idle" || stage === "compiling" || stage === "compile-fail") {
    return {
      compileHighlight: true,
      compileDisabled: stage === "compiling",
      predictHighlight: false,
      predictDisabled: true,
      runHighlight: false,
      runDisabled: true,
    }
  }
  if (stage === "compile-pass" || stage === "predicting" || stage === "predict-fail") {
    return {
      compileHighlight: false,
      compileDisabled: false,
      predictHighlight: true,
      predictDisabled: false,
      runHighlight: false,
      runDisabled: true,
    }
  }
  return {
    compileHighlight: false,
    compileDisabled: false,
    predictHighlight: false,
    predictDisabled: false,
    runHighlight: true,
    runDisabled: false,
  }
}

interface LockableButtonProps {
  disabled: boolean
  lockReason: string
  children: ReactNode
}

// Wraps a gated button so a hover Tooltip explains why it is still locked.
// A disabled button swallows pointer events, so the Tooltip trigger is a focusable
// span carrying the reason as aria-label for screen readers and hover discovery.
function LockableButton({ disabled, lockReason, children }: LockableButtonProps) {
  if (!disabled) {
    return <>{children}</>
  }
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span aria-label={lockReason} tabIndex={0} className="inline-flex">
          {children}
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" sideOffset={8}>
        {lockReason}
      </TooltipContent>
    </Tooltip>
  )
}

export function CenterActionBar({ stage, onCompile, onPredict, onRun }: CenterActionBarProps) {
  const d = deriveButtons(stage)
  return (
    <div
      data-studio-center-action-bar="true"
      className="studio-center-action-bar fixed bottom-6 left-1/2 z-40 inline-flex -translate-x-1/2 items-center gap-0 rounded-full border p-1"
    >
      <Button
        variant="ghost"
        size="default"
        disabled={d.compileDisabled}
        onClick={onCompile}
        className={`studio-center-action-button h-10 gap-1.5 rounded-full px-4 text-xs ${d.compileHighlight ? "studio-center-action-button--active" : ""}`}
      >
        <Hammer className="size-3.5" />
        Compile
      </Button>
      <LockableButton disabled={d.predictDisabled} lockReason={PREDICT_LOCK_REASON}>
        <Button
          variant="ghost"
          size="default"
          disabled={d.predictDisabled}
          onClick={onPredict}
          className={`studio-center-action-button h-10 gap-1.5 rounded-full px-4 text-xs ${d.predictHighlight ? "studio-center-action-button--active" : ""}`}
        >
          <Zap className="size-3.5" />
          Predict
        </Button>
      </LockableButton>
      <LockableButton disabled={d.runDisabled} lockReason={RUN_LOCK_REASON}>
        <Button
          variant="ghost"
          size="default"
          disabled={d.runDisabled}
          onClick={onRun}
          className={`studio-center-action-button h-10 gap-1.5 rounded-full px-4 text-xs ${d.runHighlight ? "studio-center-action-button--active" : ""}`}
        >
          <Play fill="currentColor" className="size-3.5" />
          Run
        </Button>
      </LockableButton>
    </div>
  )
}
