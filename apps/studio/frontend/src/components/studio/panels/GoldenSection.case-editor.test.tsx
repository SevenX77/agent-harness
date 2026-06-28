import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { GoldenCaseContent } from "@/api/types"
import { GoldenCaseEditor } from "./GoldenSection"

// N4 atom #29: the editable golden case view is seeded from the backend
// GoldenBaselineContent.cases[].expected_output (the content-read endpoint). This
// render-contract test asserts the editor opens that stored expected_output in an
// editable JSON Textarea, keyed by the case's node_id.
function caseFixture(overrides: Partial<GoldenCaseContent> = {}): GoldenCaseContent {
  return {
    case_id: "segment",
    node_id: "segment",
    phase_id: "segment",
    expected_output: { segments: ["a", "b"] },
    ...overrides,
  }
}

function renderEditor(goldenCase: GoldenCaseContent): string {
  return renderToStaticMarkup(
    <GoldenCaseEditor skillId="demo" goldenCase={goldenCase} onSaved={() => {}} />,
  )
}

describe("GoldenCaseEditor — editable expected_output (atom #29)", () => {
  it("seeds the textarea with the case's stored expected_output JSON", () => {
    const html = renderEditor(caseFixture())
    // The backend expected_output is rendered as pretty JSON in the editable textarea.
    expect(html).toContain("&quot;segments&quot;")
    expect(html).toContain("&quot;a&quot;")
    expect(html).toContain("&quot;b&quot;")
  })

  it("labels the editor by the case node id and offers a save action", () => {
    const html = renderEditor(caseFixture({ node_id: "review" }))
    expect(html).toContain('aria-label="Golden expected output for review"')
    expect(html).toContain("Save golden")
  })
})
