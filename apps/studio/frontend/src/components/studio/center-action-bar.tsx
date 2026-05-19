import { Hammer, Play, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"

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

export function CenterActionBar({ stage, onCompile, onPredict, onRun }: CenterActionBarProps) {
  const d = deriveButtons(stage)
  return (
    <div className="absolute bottom-6 left-1/2 z-30 inline-flex -translate-x-1/2 items-center gap-1 rounded-full border border-border bg-card px-1.5 py-1 shadow-lg">
      <Button
        variant={d.compileHighlight ? "default" : "ghost"}
        size="default"
        disabled={d.compileDisabled}
        onClick={onCompile}
        className="h-9 gap-1.5 rounded-full px-3.5 text-xs"
      >
        <Hammer className="size-3.5" />
        Compile
      </Button>
      <Button
        variant={d.predictHighlight ? "default" : "ghost"}
        size="default"
        disabled={d.predictDisabled}
        onClick={onPredict}
        className="h-9 gap-1.5 rounded-full px-3.5 text-xs"
      >
        <Zap className="size-3.5" />
        Predict
      </Button>
      <Button
        variant={d.runHighlight ? "default" : "ghost"}
        size="default"
        disabled={d.runDisabled}
        onClick={onRun}
        className="h-9 gap-1.5 rounded-full px-3.5 text-xs"
      >
        <Play fill="currentColor" className="size-3.5" />
        Run
      </Button>
    </div>
  )
}
