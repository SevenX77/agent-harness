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

export interface GateProjection {
  stage: SkillBuildStage
  effects: GateEffect[]
}

const STAGE_BY_OUTCOME: Record<SkillGate, Record<GateOutcome, SkillBuildStage>> = {
  compile: { started: "compiling", pass: "compile-pass", fail: "compile-fail", paused: "compile-pass", stopped: "compile-pass" },
  predict: { started: "predicting", pass: "predict-pass", fail: "predict-fail", paused: "predict-pass", stopped: "predict-pass" },
  // A finished run leaves the toolbar on predict-pass: the skill is still
  // predict-clean and immediately runnable again, which is the state a human sees
  // after their own run completes.
  run: { started: "running", pass: "predict-pass", fail: "run-fail", paused: "paused", stopped: "predict-pass" },
}

/**
 * Identity of a gate outcome, used to drop repeats.
 *
 * A locally projected outcome and the backend broadcast of the same outcome carry
 * the same identity, so applying both is a no-op the second time — the drawer must
 * not pop twice because the click handler and the event stream both saw it.
 */
export function gateEventKey(event: SkillGateEvent): string {
  const subject = event.runId ?? event.contentHash ?? ""
  return `${event.skillId}|${event.gate}|${event.outcome}|${subject}`
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
