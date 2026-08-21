/**
 * One projection from a gate outcome to Studio's build stage and its side effects.
 *
 * The gate state machine used to live inline in `handleCompile` / `handlePredict` /
 * `handleRun`, which meant only the person clicking a button could move it: a
 * compile driven by copilot over MCP left the toolbar parked, the error drawer
 * shut and the Trace panel unswitched. Both paths now converge here — the click
 * handler projects its own HTTP response, the event stream projects the backend's
 * `skill_gate` broadcast, and the projection cannot differ because it is the same
 * function (决议 2026-08-03「状态对等」D4).
 *
 * Kept pure on purpose: the caller performs the effects. That keeps every
 * transition assertable without a DOM, which is what the two-path parity test
 * compares.
 */

import type { CompileError, PredictDiagnosticExport } from "@/api/types"
import type { RunVerdict } from "@/utils/run-status-projection"

import type { SkillBuildStage } from "./center-action-bar"

export type SkillGate = "compile" | "predict" | "run"

const GATE_OUTCOMES = ["started", "pass", "fail", "paused", "stopped"] as const

function isGateOutcome(value: unknown): value is GateOutcome {
  return GATE_OUTCOMES.includes(value as GateOutcome)
}
/** `stopped` is the user ending a run on purpose — a terminal outcome, not a defect. */
export type GateOutcome = "started" | "pass" | "fail" | "paused" | "stopped"

export interface SkillGateEvent {
  skillId: string
  gate: SkillGate
  outcome: GateOutcome
  /** Compile artifact identity; absent for run terminal events. */
  contentHash?: string | null
  runId?: string | null
  defectCount?: number
  /**
   * The full aggregated defect set of a failed compile. Carried on the event rather
   * than re-derived by the receiver: diagnostics have one owner, and a surface that
   * recomputes its own list is exactly what the diagnostics-SSOT rule forbids.
   */
  errors?: CompileError[]
  /**
   * A failed predict's diagnostic export, so the receiver can render it with the
   * very same projection the clicking path uses instead of a parallel formatter.
   */
  predictExport?: PredictDiagnosticExport | null
}

export type GateEffect =
  | { kind: "open-drawer"; gate: SkillGate; errors: CompileError[] }
  | { kind: "close-drawers" }
  | { kind: "follow-run"; runId: string }
  /** Bring the live trace into view; predict and run both stream events into it. */
  | { kind: "open-trace" }
  /**
   * This run is over and written out, so its record can now be read: its row
   * belongs in the run list, its outcome belongs in a toast, and any node still
   * painted "running" belongs to a run that no longer is.
   *
   * `verdict` is how it ended, stated by the gate itself. Carrying it costs
   * nothing — the projection below already reads `outcome` to decide this
   * effect exists — and it is the difference between the receiver KNOWING the
   * run ended and merely knowing to go ask. The record read-back it goes on to
   * make is a round trip that can fail, and when it did there was no other
   * answer left (ledger N5).
   */
  | { kind: "finalize-run"; runId: string; verdict: RunVerdict }

export interface GateProjection {
  stage: SkillBuildStage
  effects: GateEffect[]
}

const STAGE_BY_OUTCOME: Record<SkillGate, Record<GateOutcome, SkillBuildStage>> = {
  compile: { started: "compiling", pass: "compile-pass", fail: "compile-fail", paused: "compile-pass", stopped: "compile-pass" },
  predict: { started: "predicting", pass: "predict-pass", fail: "predict-fail", paused: "predict-pass", stopped: "predict-pass" },
  // A finished run leaves the toolbar on predict-pass: the skill is still
  // predict-clean and immediately runnable again, which is the state a human sees
  // after their own run completes. A run that FAILED is a finished run too —
  // nothing about the skill changed, so pressing Run again is the obvious next
  // move. It used to land on a stage of its own, which `CenterActionBar` drew as
  // a live Run button while `Workspace.handleRun` (accepting only `predict-pass`)
  // returned in silence: the one outcome where the toolbar lied. The failure
  // still reaches the user — through the `open-drawer` effect below, which is
  // keyed on the outcome and not on the stage.
  run: { started: "running", pass: "predict-pass", fail: "predict-pass", paused: "paused", stopped: "predict-pass" },
}

/**
 * What a gate outcome means to the run-status projection, or null when the gate
 * is not describing an ending.
 *
 * The two vocabularies overlap without matching: a gate says `pass` where the
 * projection says `success`, and `stopped` where it says `cancelled`. Passing
 * a gate word straight into the slot that decides every node badge would put a
 * value the projection has never heard of into `NODE_STATUS_AT_RUN_END`, so the
 * translation is written down once, here, next to the words being translated.
 */
export function runVerdictFromGateOutcome(outcome: GateOutcome): RunVerdict | null {
  switch (outcome) {
    case "pass":
      return "success"
    case "fail":
      return "failed"
    case "paused":
      return "paused"
    case "stopped":
      return "cancelled"
    case "started":
      return null
  }
}

export function projectGateEvent(event: SkillGateEvent): GateProjection {
  const stage = STAGE_BY_OUTCOME[event.gate][event.outcome]
  const effects: GateEffect[] = []

  if (event.outcome === "fail") {
    effects.push({ kind: "open-drawer", gate: event.gate, errors: event.errors ?? [] })
  }
  if (event.outcome !== "fail") {
    effects.push({ kind: "close-drawers" })
  }
  // Predict streams its events through the same run websocket (transient predict
  // record), so BOTH started gates re-point the stream — a trace panel opened for
  // a predict must never keep showing the previous run's events (decision
  // 2026-08-07 viewed-run).
  if ((event.gate === "predict" || event.gate === "run") && event.outcome === "started" && event.runId) {
    effects.push({ kind: "follow-run", runId: event.runId })
  }
  // Predict and run both stream phase events, so both put the trace on screen —
  // and both do it from here, so a gate driven by copilot lands the human on the
  // same panel their own click would have.
  if ((event.gate === "predict" || event.gate === "run") && event.outcome === "started") {
    effects.push({ kind: "open-trace" })
  }
  // A predict is a run for everything that happens at the end of one: it has a
  // directory, an account, a `run_ended`, a row in the same list and the same
  // node badges. Only a compile produces no run, and only "started" is not an
  // ending — so those two are the exclusions, not the gate's name. "Is this an
  // ending" is asked by translating the outcome, so the two places that decide
  // it cannot drift into disagreeing.
  const verdict = runVerdictFromGateOutcome(event.outcome)
  if (event.gate !== "compile" && verdict && event.runId) {
    effects.push({ kind: "finalize-run", runId: event.runId, verdict })
  }

  return { stage, effects }
}

/** Parse one raw `skill_gate` websocket payload; returns null when it is not one. */
export function parseSkillGateEvent(raw: Record<string, unknown>): SkillGateEvent | null {
  if (raw.type !== "skill_gate") return null
  const skillId = typeof raw.skill_id === "string" ? raw.skill_id : ""
  const gate = raw.gate
  const outcome = raw.outcome
  if (!skillId) return null
  if (gate !== "compile" && gate !== "predict" && gate !== "run") return null
  if (!isGateOutcome(outcome)) return null
  return {
    skillId,
    gate,
    outcome,
    contentHash: typeof raw.content_hash === "string" ? raw.content_hash : null,
    runId: typeof raw.run_id === "string" ? raw.run_id : null,
    defectCount: typeof raw.defect_count === "number" ? raw.defect_count : 0,
    errors: Array.isArray(raw.errors) ? (raw.errors as CompileError[]) : undefined,
    predictExport: (raw.predict_export as PredictDiagnosticExport | undefined) ?? null,
  }
}
