import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { EdgeContextView } from "./EdgeContextView"
import type { SelectedEdge } from "../WorkspaceContext"

function render(edge: SelectedEdge): string {
  return renderToStaticMarkup(<EdgeContextView selectedEdge={edge} onClear={() => undefined} />)
}

describe("EdgeContextView", () => {
  it("frames the dot as a blackboard transition (source -> target), not node I/O", () => {
    const html = render({
      id: "a->b",
      source: "segment",
      target: "expand",
      contextJson: {
        inputs: { topic: "cats" },
        blackboard_snapshot: { topic: "cats" },
        changed_keys: ["topic"],
        phase_outputs: {},
      },
    })
    expect(html).toContain("Blackboard transition")
    expect(html).toContain("segment")
    expect(html).toContain("expand")
    // The removed Properties dump's node-I/O framing must not reappear here.
    expect(html).not.toContain("Input Arguments")
    expect(html).not.toContain("Full Frame Trace")
    expect(html).not.toContain("Copy JSON")
  })

  it("surfaces changed_keys and the dispatched blackboard fields", () => {
    const html = render({
      id: "a->b",
      source: "a",
      target: "b",
      contextJson: {
        blackboard_snapshot: { topic: "cats", count: 3 },
        changed_keys: ["count"],
      },
    })
    expect(html).toContain("Keys changed at this transition")
    expect(html).toContain("count")
    expect(html).toContain("topic")
    expect(html).toContain("cats")
  })

  it("shows an honest empty state when no transition was recorded", () => {
    const html = render({ id: "a->b", source: "a", target: "b", contextJson: undefined })
    expect(html).toContain("No transition recorded for this edge")
  })

  it("renders the static field inference when the edge has not run yet (n5 atom #14)", () => {
    const html = render({
      id: "enrich->report",
      source: "enrich",
      target: "report",
      contextJson: {
        kind: "static_inference",
        source: "enrich",
        target: "report",
        fields: [
          { name: "summary", type: "string", from: "enrich", via_file: false, consumed_by_target: true },
          { name: "style_guide", type: "string", from: "references/style.md", via_file: true, consumed_by_target: true },
          { name: "topic", type: "string", from: "input", via_file: false, consumed_by_target: false },
        ],
      },
    })

    expect(html).toContain("Inferred blackboard fields")
    expect(html).toContain("summary")
    expect(html).toContain("style_guide")
    expect(html).toContain("references/style.md")
    expect(html).toContain("topic")
    // Consumed-by-target fields are marked as the dispatch boundary.
    expect(html).toContain("report input")
    // No runtime affordances before a run exists.
    expect(html).not.toContain("Tamper")
    expect(html).not.toContain("Resume downstream")
    expect(html).not.toContain("Operations (end → start)")
    expect(html).not.toContain("No transition recorded for this edge")
  })

  it("offers explicit Tamper editing and downstream resume from a real checkpointed edge context", () => {
    const html = render({
      id: "draft->review",
      source: "draft",
      target: "review",
      contextJson: {
        blackboard_snapshot: { topic: "cats" },
        checkpoint_id: "checkpoint-review",
        checkpoint_ns: "agent:review",
      },
    })

    expect(html).toContain("Tamper")
    expect(html).toContain("Resume downstream")
    expect(html).toContain('aria-label="Tampered edge context JSON"')
    expect(html).toContain("checkpoint-review")
  })

  it("keeps the original trace frame read-only while showing tamper diff and audit", () => {
    const html = render({
      id: "draft->review",
      source: "draft",
      target: "review",
      contextJson: {
        blackboard_snapshot: { topic: "cats" },
        checkpoint_id: "checkpoint-review",
        checkpoint_ns: "agent:review",
        tamper_diff: {
          changed_keys: ["topic"],
          before: { topic: "cats" },
          after: { topic: "dogs" },
        },
        tamper_audit: {
          event_type: "resume_applied",
          context_override_keys: ["topic"],
        },
      },
    })

    expect(html).toContain("Original trace frame")
    expect(html).toContain("cats")
    expect(html).toContain("Tamper diff")
    expect(html).toContain("dogs")
    expect(html).toContain("Tamper audit")
    expect(html).toContain("resume_applied")
    expect(html).toContain("context_override_keys")
  })

  it("renders the end -> start operation log (reduce / dispatch / inject / persist) from real operations", () => {
    const html = render({
      id: "planner->executor",
      source: "planner",
      target: "executor",
      contextJson: {
        blackboard_snapshot: { plan: "x" },
        changed_keys: ["plan"],
        operations: [
          { kind: "reduce", reducer: "merge_dicts", changed_keys: ["plan"] },
          { kind: "persist", name: "plan.json", path: "runs/r1/plan.json", size_bytes: 128 },
          { kind: "inject", file_ref: "runs/r1/plan.json", target_field: "spec" },
          { kind: "dispatch", dispatched_keys: ["plan", "spec"], changed_keys: ["plan", "spec"] },
        ],
      },
    })

    expect(html).toContain("Operations (end → start)")
    // The stale target-design placeholder must be gone.
    expect(html).not.toContain("target-design")
    expect(html).toContain("reduce")
    expect(html).toContain("merge_dicts")
    expect(html).toContain("persist")
    expect(html).toContain("plan.json")
    expect(html).toContain("runs/r1/plan.json")
    expect(html).toContain("inject")
    expect(html).toContain("spec")
    expect(html).toContain("dispatch")
  })

  it("shows an honest empty operation log when no operations were recorded", () => {
    const html = render({
      id: "planner->executor",
      source: "planner",
      target: "executor",
      contextJson: {
        blackboard_snapshot: { plan: "x" },
        changed_keys: ["plan"],
        operations: [],
      },
    })

    expect(html).toContain("Operations (end → start)")
    expect(html).toContain("No operations recorded for this transition")
  })

  it("disables downstream resume when edge checkpoint validity is dirty upstream", () => {
    const html = render({
      id: "draft->review",
      source: "draft",
      target: "review",
      contextJson: {
        blackboard_snapshot: { topic: "cats" },
        checkpoint_id: "checkpoint-review",
        checkpoint_ns: "agent:review",
        resume_validity: {
          resume_allowed: false,
          reason: "dirty_upstream",
          dirty_fields: ["execution_fingerprint"],
        },
      },
    })

    expect(html).toContain("dirty_upstream")
    expect(html).toContain("Resume disabled")
    const resumeSlice = html.slice(html.indexOf("Resume disabled") - 240, html.indexOf("Resume disabled") + 160)
    expect(resumeSlice).toContain('disabled=""')
  })
})
