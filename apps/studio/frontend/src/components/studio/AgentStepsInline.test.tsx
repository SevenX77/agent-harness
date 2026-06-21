import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import { AgentStepsInline, AgentStepsInlineView } from "./AgentStepsInline"
import { parseAgentSteps } from "@/lib/agent-steps"

const BODY = `<role>r</role>

<step id="S1" name="read">
Read it.
</step>

<step id="S2" name="finish">
Finish it.
</step>
`

const noop = () => undefined

describe("AgentStepsInlineView", () => {
  it("renders each step's id, name and content with edit controls", () => {
    const html = renderToStaticMarkup(
      <AgentStepsInlineView
        steps={parseAgentSteps(BODY)}
        onMove={noop}
        onRemove={noop}
        onRename={noop}
        onEditContent={noop}
        onAdd={noop}
      />,
    )
    expect(html).toContain("Steps")
    expect(html).toContain("S1")
    expect(html).toContain("read")
    expect(html).toContain("Read it.")
    expect(html).toContain("Add step")
    expect(html).toContain("Move step S1 up")
    expect(html).toContain("Remove step S2")
  })

  it("hides edit controls in readOnly mode", () => {
    const html = renderToStaticMarkup(
      <AgentStepsInlineView
        steps={parseAgentSteps(BODY)}
        readOnly
        onMove={noop}
        onRemove={noop}
        onRename={noop}
        onEditContent={noop}
        onAdd={noop}
      />,
    )
    expect(html).toContain("S1")
    expect(html).not.toContain("Add step")
    expect(html).not.toContain("Remove step")
  })

  it("shows an empty state when there are no steps", () => {
    const html = renderToStaticMarkup(
      <AgentStepsInlineView
        steps={[]}
        onMove={noop}
        onRemove={noop}
        onRename={noop}
        onEditContent={noop}
        onAdd={noop}
      />,
    )
    expect(html).toContain("No steps yet.")
  })
})

describe("AgentStepsInline reorder", () => {
  it("moving S1 down emits a body with S2 then S1", () => {
    const onSave = vi.fn()
    // Render the wrapper to capture the onMove it wires, then invoke it.
    // (renderToStaticMarkup runs the component body, building the handlers.)
    const tree = AgentStepsInline({ body: BODY, onSave }) as ReturnType<typeof AgentStepsInlineView>
    // tree is <AgentStepsInlineView ... onMove=move .../> — pull the wired handler.
    const move = (tree.props as { onMove: (id: string, dir: "up" | "down") => void }).onMove
    move("S1", "down")
    expect(onSave).toHaveBeenCalledTimes(1)
    const nextBody = onSave.mock.calls[0][0] as string
    expect(parseAgentSteps(nextBody).map((s) => s.id)).toEqual(["S2", "S1"])
  })
})
