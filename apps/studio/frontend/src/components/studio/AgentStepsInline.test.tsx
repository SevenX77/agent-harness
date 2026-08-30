import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { AgentStepsInline } from "./AgentStepsInline"

const BODY = `<role>r</role>

<step id="S1" name="read">
Read it.
</step>

<step id="S2" name="finish">
Finish it.
</step>
`

/**
 * R3-8 (批示轮三 2026-08-29) reverses F5's canvas-inline EDITING: the user
 * ruled 「在画布上加step这个功能去掉吧,很鸡肋,应该让用户在编辑器改」.
 * The inline sub-nodes stay as a READ-ONLY projection (the runtime debug
 * bar's 对话续跑 still targets them); every mutation control is gone —
 * editing the body happens in the editor.
 */
describe("AgentStepsInline (read-only projection)", () => {
  it("renders each step's id, name and content as plain text", () => {
    const html = renderToStaticMarkup(<AgentStepsInline body={BODY} />)
    expect(html).toContain("Steps")
    expect(html).toContain("S1")
    expect(html).toContain("read")
    expect(html).toContain("Read it.")
    expect(html).toContain("S2")
    expect(html).toContain("Finish it.")
  })

  it("offers no mutation controls and no form fields", () => {
    const html = renderToStaticMarkup(<AgentStepsInline body={BODY} />)
    expect(html).not.toContain("Add step")
    expect(html).not.toContain("Remove step")
    expect(html).not.toContain("Move step")
    expect(html).not.toContain("<input")
    expect(html).not.toContain("<textarea")
  })

  it("shows an empty state when there are no steps", () => {
    const html = renderToStaticMarkup(<AgentStepsInline body="<role>r</role>" />)
    expect(html).toContain("No steps yet.")
  })
})
