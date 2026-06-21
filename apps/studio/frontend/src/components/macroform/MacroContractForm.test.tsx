import { renderToStaticMarkup } from "react-dom/server"
import type { ComponentProps, ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { MacroContractForm } from "./MacroContractForm"
import { applyGraphHeaderForm, graphHeaderToForm } from "./graph-header"
import type { GraphHeaderFormData } from "./graph-header"

vi.mock("../ui/badge", () => ({
  Badge: ({ children, ...props }: ComponentProps<"span"> & { children: ReactNode }) => (
    <span data-slot="badge" {...props}>
      {children}
    </span>
  ),
}))

vi.mock("../ui/button", () => ({
  Button: ({ children, ...props }: ComponentProps<"button"> & { children: ReactNode }) => (
    <button data-slot="button" {...props}>
      {children}
    </button>
  ),
}))

vi.mock("../ui/input", () => ({
  Input: (props: ComponentProps<"input">) => <input data-slot="input" {...props} />,
}))

vi.mock("../ui/label", () => ({
  Label: ({ children, ...props }: ComponentProps<"label"> & { children: ReactNode }) => (
    <label data-slot="label" {...props}>
      {children}
    </label>
  ),
}))

vi.mock("../ui/textarea", () => ({
  Textarea: (props: ComponentProps<"textarea">) => <textarea data-slot="textarea" {...props} />,
}))

vi.mock("../ui/select", () => ({
  Select: ({ children }: { children: ReactNode }) => <div data-slot="select">{children}</div>,
  SelectContent: ({ children }: { children: ReactNode }) => (
    <div data-slot="select-content">{children}</div>
  ),
  SelectItem: ({ children }: { children: ReactNode }) => (
    <div data-slot="select-item">{children}</div>
  ),
  SelectTrigger: ({ children }: { children: ReactNode }) => (
    <button data-slot="select-trigger">{children}</button>
  ),
  SelectValue: ({ placeholder }: { placeholder?: string }) => (
    <span data-slot="select-value">{placeholder}</span>
  ),
}))

const data: GraphHeaderFormData = {
  name: "event-extraction-v2",
  schemaVersion: "v0.3.0",
  llmRole: "analyst",
  description: "Extract event timeline.",
  phases: ["setup", "aggregate"],
}

const GRAPH_MD = [
  "---",
  'schema_version: "v0.3.0"',
  "name: event-extraction-v2",
  "description: Extract event timeline from ABC-segmented paragraphs.",
  "io:",
  "  inputs:",
  "    type: object",
  "    properties:",
  "      segmentation_result:",
  "        type: object",
  "  outputs:",
  "    type: object",
  "    properties:",
  "      event_timeline:",
  "        type: object",
  "phases: [setup, aggregate, review, settings]",
  "---",
  "",
  "<phase>setup</phase>",
  "",
].join("\n")

describe("MacroContractForm", () => {
  it("renders structured shadcn fields for the four scalar header fields + a phases list, no type entry", () => {
    const html = renderToStaticMarkup(
      <MacroContractForm
        data={data}
        onChange={vi.fn()}
        onSaveHeader={vi.fn()}
        onSavePhases={vi.fn()}
      />,
    )

    // name / schema_version inputs, description textarea, llm_role select.
    expect(html).toContain('data-slot="input"')
    expect(html).toContain('data-slot="textarea"')
    expect(html).toContain('data-slot="select"')
    expect(html).toContain("Name")
    expect(html).toContain("Schema version")
    expect(html).toContain("LLM role")
    expect(html).toContain("Description")
    // phases add/remove list.
    expect(html).toContain("Phases")
    expect(html).toContain('data-slot="badge"')
    expect(html).toContain("setup")
    expect(html).toContain("aggregate")
    // two save paths (header scalars vs phases topology).
    expect(html).toContain("Save header")
    expect(html).toContain("Save phases")
    // FROZEN: no type/mode entry in the header form.
    expect(html).not.toContain(">Type<")
    expect(html).not.toContain(">Mode<")
    // code-like fields disable autocorrection.
    expect(html).toContain('spellCheck="false"')
    expect(html).toContain('autoCorrect="off"')
  })
})

describe("graphHeaderToForm / applyGraphHeaderForm", () => {
  it("reads the four scalar header fields + phases from GRAPH.md frontmatter", () => {
    const form = graphHeaderToForm(GRAPH_MD)
    expect(form.name).toBe("event-extraction-v2")
    expect(form.schemaVersion).toBe("v0.3.0")
    expect(form.description).toBe("Extract event timeline from ABC-segmented paragraphs.")
    expect(form.phases).toEqual(["setup", "aggregate", "review", "settings"])
  })

  it("re-renders the header with edited name while preserving io / phases / body and never emitting type", () => {
    const baseForm = graphHeaderToForm(GRAPH_MD)
    const result = applyGraphHeaderForm(GRAPH_MD, { ...baseForm, name: "renamed-graph" })
    expect(result.ok).toBe(true)
    if (!result.ok) return
    // edited scalar is written.
    expect(result.markdown).toContain("name: renamed-graph")
    // topology + io + body bytes the form does not own are preserved.
    expect(result.markdown).toContain("phases:")
    expect(result.markdown).toContain("review")
    expect(result.markdown).toContain("settings")
    expect(result.markdown).toContain("event_timeline")
    expect(result.markdown).toContain("<phase>setup</phase>")
    // FROZEN: no type field is ever emitted into the header.
    expect(result.markdown).not.toContain("type: simple")
    expect(result.markdown).not.toMatch(/^type:/m)
  })

  it("drops llm_role when cleared but keeps it when set (optional header field)", () => {
    const baseForm = graphHeaderToForm(GRAPH_MD)
    const withRole = applyGraphHeaderForm(GRAPH_MD, { ...baseForm, llmRole: "planner" })
    expect(withRole.ok).toBe(true)
    if (withRole.ok) {
      expect(withRole.markdown).toContain("llm_role: planner")
    }
    const cleared = applyGraphHeaderForm(GRAPH_MD, { ...baseForm, llmRole: "" })
    expect(cleared.ok).toBe(true)
    if (cleared.ok) {
      expect(cleared.markdown).not.toContain("llm_role:")
    }
  })
})
