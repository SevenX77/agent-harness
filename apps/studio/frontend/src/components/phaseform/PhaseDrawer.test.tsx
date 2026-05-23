import { renderToStaticMarkup } from "react-dom/server"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import type { PhaseFormData } from "../../hooks/usePhaseForm"
import { PhaseDrawer } from "./PhaseDrawer"

vi.mock("../ui/button", () => ({
  Button: ({
    children,
    className,
    disabled,
  }: {
    children: ReactNode
    className?: string
    disabled?: boolean
  }) => (
    <button className={className} data-disabled={disabled} data-slot="button">
      {children}
    </button>
  ),
}))

vi.mock("../ui/sheet", () => ({
  Sheet: ({ children, open }: { children: ReactNode; open?: boolean }) => (
    open ? <div data-slot="sheet">{children}</div> : null
  ),
  SheetContent: ({
    children,
    className,
  }: {
    children: ReactNode
    className?: string
  }) => (
    <aside className={className} data-slot="sheet-content">
      {children}
    </aside>
  ),
  SheetDescription: ({ children }: { children: ReactNode }) => (
    <p data-slot="sheet-description">{children}</p>
  ),
  SheetFooter: ({ children }: { children: ReactNode }) => (
    <div data-slot="sheet-footer">{children}</div>
  ),
  SheetHeader: ({ children }: { children: ReactNode }) => (
    <div data-slot="sheet-header">{children}</div>
  ),
  SheetTitle: ({ children }: { children: ReactNode }) => (
    <h2 data-slot="sheet-title">{children}</h2>
  ),
}))

vi.mock("./PhaseFormBody", () => ({
  PhaseFormBody: () => <div data-slot="phase-form-body" />,
}))

const data: PhaseFormData = {
  name: "Plan",
  mode: "llm",
  llmRole: "",
  prompt: "Summarize the task.",
  userPromptTemplate: "",
  agentTools: [],
  modelOverride: "",
  executeSteps: [],
  validator: "",
  when: "",
  skipIf: "",
}

describe("PhaseDrawer", () => {
  it("uses shadcn sheet and button primitives instead of a custom focus trap drawer", () => {
    const html = renderToStaticMarkup(
      <PhaseDrawer
        open
        phaseId="plan"
        data={data}
        availableTools={[]}
        dirty={false}
        onChange={vi.fn()}
        onApply={vi.fn()}
        onReset={vi.fn()}
        onClose={vi.fn()}
      />,
    )

    expect(html).toContain('data-slot="sheet-content"')
    expect(html).toContain('data-slot="sheet-title"')
    expect(html).toContain('data-slot="button"')
    expect(html).not.toContain('role="dialog"')
    expect(html).not.toContain("fixed inset-0")
    expect(html).not.toContain("bg-slate")
    expect(html).not.toContain("text-slate")
    expect(html).not.toContain("bg-sky")
  })
})
