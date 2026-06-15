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
})
