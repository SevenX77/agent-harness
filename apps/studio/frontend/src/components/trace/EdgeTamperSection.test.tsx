import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { EdgeTamperSection } from "./EdgeTamperSection"
import type { SelectedEdge } from "../studio/WorkspaceContext"

// What survives of EdgeContextView (decision 2026-08-13 D5): the tamper
// OPERATION and the pre-run static inference. The semantic display —
// transition framing, changed keys, the operation log — retired into the
// trace rows and is deliberately not re-asserted here.

function render(edge: SelectedEdge): string {
  return renderToStaticMarkup(
    <EdgeTamperSection selectedEdge={edge} onResumeDownstream={() => undefined} />,
  )
}

describe("EdgeTamperSection", () => {
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
  })

  it("renders the static field inference when the edge has not run yet (n5 atom #14)", () => {
    const html = render({
      id: "input->draft",
      source: "__global_input__",
      target: "draft",
      contextJson: {
        kind: "static_inference",
        fields: [
          { name: "topic", type: "string", from: "input", via_file: false, consumed_by_target: true },
        ],
      } as unknown as SelectedEdge["contextJson"],
    })

    expect(html).toContain("Inferred blackboard fields")
    expect(html).toContain("topic")
  })

  it("shows what the run produced at the Output boundary, and offers no resume there", () => {
    // The Output boundary is a canvas pseudo-node: nothing runs after it, so
    // "tamper the context and resume downstream" has no downstream to aim at —
    // `resumeFromNodeId` would be an id the engine has never heard of. What the
    // dot owes the reader here is the run's produced values (ledger E14).
    const html = render({
      id: "global_synthesis->__global_output__",
      source: "global_synthesis",
      target: "__global_output__",
      contextJson: {
        blackboard_snapshot: { story_framework: { acts: 3 } },
        from_phase: "global_synthesis",
        to_phase: "__global_output__",
        changed_keys: ["story_framework"],
      },
    })

    expect(html).toContain("Run output")
    expect(html).toContain("global_synthesis")
    expect(html).toContain("story_framework")
    expect(html).not.toContain("Tamper")
    expect(html).not.toContain("Resume downstream")
  })

  it("shows an honest empty state when no transition was recorded", () => {
    const html = render({ id: "draft->review", source: "draft", target: "review" })
    expect(html).toContain("No transition recorded")
  })
})
