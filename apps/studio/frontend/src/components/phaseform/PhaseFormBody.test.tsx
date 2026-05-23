import { renderToStaticMarkup } from "react-dom/server"
import type { ComponentProps, ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import type { PhaseFormData } from "../../hooks/usePhaseForm"
import { PhaseFormBody } from "./PhaseFormBody"

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

vi.mock("../ui/collapsible", () => ({
  Collapsible: ({ children }: { children: ReactNode }) => <div data-slot="collapsible">{children}</div>,
  CollapsibleContent: ({ children }: { children: ReactNode }) => (
    <div data-slot="collapsible-content">{children}</div>
  ),
  CollapsibleTrigger: ({ children }: { children: ReactNode }) => (
    <button data-slot="collapsible-trigger">{children}</button>
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

vi.mock("../ui/textarea", () => ({
  Textarea: (props: ComponentProps<"textarea">) => <textarea data-slot="textarea" {...props} />,
}))

const data: PhaseFormData = {
  name: "Plan",
  mode: "llm",
  llmRole: "planner",
  prompt: "Plan the task.",
  userPromptTemplate: "",
  agentTools: ["script.search"],
  modelOverride: "",
  executeSteps: [],
  when: "context.ready",
  skipIf: "",
  validator: "script.validate",
}

describe("PhaseFormBody", () => {
  it("uses shadcn field primitives and disables text autocorrection for code-like values", () => {
    const html = renderToStaticMarkup(
      <PhaseFormBody
        data={data}
        availableTools={["script.search", "script.write"]}
        onChange={vi.fn()}
      />,
    )

    expect(html).toContain('data-slot="input"')
    expect(html).toContain('data-slot="textarea"')
    expect(html).toContain('data-slot="select"')
    expect(html).toContain('data-slot="button"')
    expect(html).toContain('data-slot="badge"')
    expect(html).toContain('data-slot="collapsible"')
    expect(html).toContain('spellCheck="false"')
    expect(html).toContain('autoCorrect="off"')
    expect(html).not.toContain("<select")
    expect(html).not.toContain("bg-slate")
    expect(html).not.toContain("text-slate")
    expect(html).not.toContain("focus:ring-sky")
  })
})
