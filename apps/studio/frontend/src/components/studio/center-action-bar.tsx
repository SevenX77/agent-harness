import { useLayoutEffect, useRef, type ReactNode } from "react"
import { Hammer, Pause, Play, Square, Zap } from "lucide-react"
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
  | "paused"

interface CenterActionBarProps {
  stage: SkillBuildStage
  /**
   * dead-sidecar-says-so (2026-08-24): `false` while RuntimeGate has detected
   * the backend is unreachable — every button in this bar calls into the
   * sidecar (compile/predict/run/pause/resume/stop), so every one of them
   * disables WITH a reason (not a silent grey button — the same lock-reason
   * affordance already used for the compile/predict/run stage gates below).
   * `undefined`/`true` leaves the normal stage-driven gating untouched.
   */
  backendReachable?: boolean
  onCompile?: () => void
  onPredict?: () => void
  onRun?: () => void
  onPause?: () => void
  onResume?: () => void
  onStop?: () => void
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
const BACKEND_UNAVAILABLE_REASON = "Backend unavailable — reconnecting"

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

export function CenterActionBar({
  stage,
  backendReachable,
  onCompile,
  onPredict,
  onRun,
  onPause,
  onResume,
  onStop,
}: CenterActionBarProps) {
  const staged = deriveButtons(stage)
  // The backend-unavailable override always wins: every button in the bar
  // calls the sidecar, so none of them can stay live while it's unreachable,
  // regardless of what stage the build happens to be in.
  const backendUnavailable = backendReachable === false
  const d: ButtonDerivation = backendUnavailable
    ? {
        compileHighlight: staged.compileHighlight,
        compileDisabled: true,
        predictHighlight: staged.predictHighlight,
        predictDisabled: true,
        runHighlight: staged.runHighlight,
        runDisabled: true,
      }
    : staged
  const predictLockReason = backendUnavailable ? BACKEND_UNAVAILABLE_REASON : PREDICT_LOCK_REASON
  const runLockReason = backendUnavailable ? BACKEND_UNAVAILABLE_REASON : RUN_LOCK_REASON
  const barRef = useRef<HTMLDivElement>(null)
  // Its own width, published so the clamp below can reason about its edges.
  // Measured rather than assumed: the bar's labels change with the stage.
  useLayoutEffect(() => {
    const bar = barRef.current
    if (!bar) return
    bar.style.setProperty("--studio-action-bar-width", `${bar.offsetWidth}px`)
  }, [stage])
  return (
    <div
      ref={barRef}
      data-studio-center-action-bar="true"
      className="studio-center-action-bar absolute bottom-6 z-40 inline-flex -translate-x-1/2 items-center gap-0 rounded-full border p-1"
      style={{
        // Centred on the canvas host and held there: recentring on the gap between
        // the side overlays made the bar jump sideways every time a panel opened
        // or closed, since both panels float above the canvas rather than shrink
        // it. It gives way only when an overlay would actually cover it — a panel
        // dragged wide on a narrow window — which is the case that once slid it
        // under the copilot panel. `100%` is the canvas host this sits in.
        left: `clamp(
          calc(var(--studio-canvas-left-safe-area, 0px) + var(--studio-action-bar-width, 0px) / 2),
          50%,
          calc(100% - var(--studio-canvas-right-safe-area, 0px) - var(--studio-action-bar-width, 0px) / 2)
        )`,
      }}
    >
      <LockableButton disabled={backendUnavailable} lockReason={BACKEND_UNAVAILABLE_REASON}>
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
      </LockableButton>
      <LockableButton disabled={d.predictDisabled} lockReason={predictLockReason}>
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
      {stage === "running" ? (
        // A disabled Run button says "wait" without saying how to not wait, and
        // a run in flight has the SAME two futures a paused one has: hold it,
        // or end it. Both are offered outright. Pausing keeps the checkpoint —
        // the engine only clears those when a run finishes on its own — while
        // stopping ends it here, and the backend takes either in one step, so
        // routing "stop" through a pause the reader never asked for was the UI
        // inventing a detour the run itself does not require.
        <>
          <LockableButton disabled={backendUnavailable} lockReason={BACKEND_UNAVAILABLE_REASON}>
            <Button
              variant="ghost"
              size="default"
              disabled={backendUnavailable}
              onClick={onPause}
              className="studio-center-action-button studio-center-action-button--active h-10 gap-1.5 rounded-full px-4 text-xs"
            >
              <Pause fill="currentColor" className="size-3.5" />
              Pause
            </Button>
          </LockableButton>
          <LockableButton disabled={backendUnavailable} lockReason={BACKEND_UNAVAILABLE_REASON}>
            <Button
              variant="ghost"
              size="default"
              disabled={backendUnavailable}
              onClick={onStop}
              className="studio-center-action-button h-10 gap-1.5 rounded-full px-4 text-xs"
            >
              <Square fill="currentColor" className="size-3.5" />
              Stop
            </Button>
          </LockableButton>
        </>
      ) : stage === "paused" ? (
        // A paused run has two futures and both are offered outright: carry on
        // from the checkpoint, or end it here. Neither is implied by the other.
        <>
          <LockableButton disabled={backendUnavailable} lockReason={BACKEND_UNAVAILABLE_REASON}>
            <Button
              variant="ghost"
              size="default"
              disabled={backendUnavailable}
              onClick={onResume}
              className="studio-center-action-button studio-center-action-button--active h-10 gap-1.5 rounded-full px-4 text-xs"
            >
              <Play fill="currentColor" className="size-3.5" />
              Resume
            </Button>
          </LockableButton>
          <LockableButton disabled={backendUnavailable} lockReason={BACKEND_UNAVAILABLE_REASON}>
            <Button
              variant="ghost"
              size="default"
              disabled={backendUnavailable}
              onClick={onStop}
              className="studio-center-action-button h-10 gap-1.5 rounded-full px-4 text-xs"
            >
              <Square fill="currentColor" className="size-3.5" />
              Stop
            </Button>
          </LockableButton>
        </>
      ) : (
        <LockableButton disabled={d.runDisabled} lockReason={runLockReason}>
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
      )}
    </div>
  )
}
