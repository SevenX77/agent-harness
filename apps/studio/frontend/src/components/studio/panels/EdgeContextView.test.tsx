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
