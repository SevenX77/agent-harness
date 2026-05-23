import { renderToStaticMarkup } from "react-dom/server"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { SkillCreatorWizard } from "./SkillCreatorWizard"

vi.mock("../../hooks/useSkillCreator", () => ({
  useSkillCreator: () => ({
    state: {
      stepIndex: 0,
      submitting: false,
      data: {
        templateId: "blank",
        skillId: "demo-skill",
        name: "Demo Skill",
        description: "",
        tags: "",
        inputs: [],
      },
    },
    dispatch: vi.fn(),
    preview: "",
    canNext: true,
    isLastStep: false,
    stepCount: 5,
    currentErrors: {},
  }),
  validateStep: () => ({}),
}))

vi.mock("../ui/button", () => ({
  Button: ({ children }: { children: ReactNode }) => <button data-slot="button">{children}</button>,
}))

vi.mock("../ui/dialog", () => ({
  Dialog: ({ children }: { children: ReactNode }) => <div data-slot="dialog">{children}</div>,
  DialogContent: ({ children }: { children: ReactNode }) => <div data-slot="dialog-content">{children}</div>,
  DialogDescription: ({ children }: { children: ReactNode }) => <p data-slot="dialog-description">{children}</p>,
  DialogFooter: ({ children }: { children: ReactNode }) => <div data-slot="dialog-footer">{children}</div>,
  DialogHeader: ({ children }: { children: ReactNode }) => <div data-slot="dialog-header">{children}</div>,
  DialogTitle: ({ children }: { children: ReactNode }) => <h1 data-slot="dialog-title">{children}</h1>,
}))

vi.mock("../templates/TemplatePicker", () => ({
  TemplatePicker: () => <div data-testid="template-picker" />,
}))

vi.mock("./StepIndicator", () => ({
  StepIndicator: () => <div data-testid="step-indicator" />,
}))

vi.mock("./steps/StepBasics", () => ({ StepBasics: () => null }))
vi.mock("./steps/StepFirstPhase", () => ({ StepFirstPhase: () => null }))
vi.mock("./steps/StepInputs", () => ({ StepInputs: () => null }))
vi.mock("./steps/StepPreview", () => ({ StepPreview: () => null }))

describe("SkillCreatorWizard", () => {
  it("uses shadcn dialog and button primitives for the wizard shell", () => {
    const html = renderToStaticMarkup(
      <SkillCreatorWizard
        open
        onClose={vi.fn()}
        onCreated={vi.fn()}
        pushToast={vi.fn()}
      />,
    )

    expect(html).toContain('data-slot="dialog-content"')
    expect(html).toContain('data-slot="dialog-footer"')
    expect(html).toContain('data-slot="button"')
    expect(html).not.toContain("fixed inset-0")
    expect(html).not.toContain("bg-slate")
    expect(html).not.toContain("bg-gray")
  })
})
