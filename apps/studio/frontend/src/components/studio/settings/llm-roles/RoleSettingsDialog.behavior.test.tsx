// @vitest-environment jsdom
import { act, type InputHTMLAttributes, type ReactNode } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, describe, expect, it, vi } from "vitest"
import { RoleSettingsFields, RoleSettingsPanel, type RoleSettingsDraft } from "./RoleSettingsDialog"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

vi.mock("@/components/ui/slider", () => ({
  Slider: ({
    value,
    onValueChange,
    onValueCommit,
    ...props
  }: {
    value: number[]
    onValueChange?: (value: number[]) => void
    onValueCommit?: (value: number[]) => void
  } & InputHTMLAttributes<HTMLInputElement>) => (
    <input
      {...props}
      type="range"
      value={value[0]}
      onChange={(event) => onValueChange?.([Number(event.currentTarget.value)])}
      onBlur={(event) => onValueCommit?.([Number(event.currentTarget.value)])}
    />
  ),
}))

function renderJsx(node: ReactNode): { container: HTMLDivElement; root: Root } {
  const container = document.createElement("div")
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(node)
  })
  return { container, root }
}

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set
  act(() => {
    setter?.call(input, value)
    input.dispatchEvent(new Event("input", { bubbles: true }))
  })
}

function commitInput(input: HTMLInputElement) {
  act(() => {
    input.dispatchEvent(new FocusEvent("focusout", { bubbles: true }))
  })
}

function finishPointerInteraction(input: HTMLInputElement) {
  act(() => {
    input.dispatchEvent(new Event("pointerup", { bubbles: true }))
  })
}

describe("RoleSettingsFields behavior", () => {
  afterEach(() => {
    document.body.innerHTML = ""
    vi.clearAllMocks()
  })

  it("previews temperature while dragging and submits only when the slider commits", () => {
    const onSubmit = vi.fn()
    const { container, root } = renderJsx(
      <RoleSettingsPanel
        roleName="graph_agent"
        modelFallbackEnabled={true}
        intent={{
          provider_preference: "manual_order",
          thinking: true,
          max_output_tokens: 128000,
          temperature: 0.4,
        }}
        tokenLimitSummary={{
          context: { knownCount: 0, totalCount: 0, min: null, max: null },
          output: { knownCount: 0, totalCount: 0, min: null, max: null },
        }}
        onModelFallbackChange={vi.fn()}
        onSubmit={onSubmit}
      />,
    )

    const slider = container.querySelector("[data-role-temperature-input]") as HTMLInputElement
    setInputValue(slider, "1.4")

    expect(container.textContent).toContain("70%")
    expect(onSubmit).not.toHaveBeenCalled()

    commitInput(slider)

    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit).toHaveBeenCalledWith({
      provider_preference: "manual_order",
      thinking: true,
      max_output_tokens: 128000,
      temperature: 1.4,
    })

    act(() => root.unmount())
  })

  it("submits a pending temperature preview when the pointer interaction ends", () => {
    const onSubmit = vi.fn()
    const { container, root } = renderJsx(
      <RoleSettingsPanel
        roleName="graph_agent"
        modelFallbackEnabled={true}
        intent={{
          provider_preference: "manual_order",
          thinking: true,
          max_output_tokens: 128000,
          temperature: 1.4,
        }}
        tokenLimitSummary={{
          context: { knownCount: 0, totalCount: 0, min: null, max: null },
          output: { knownCount: 0, totalCount: 0, min: null, max: null },
        }}
        onModelFallbackChange={vi.fn()}
        onSubmit={onSubmit}
      />,
    )

    const slider = container.querySelector("[data-role-temperature-input]") as HTMLInputElement
    setInputValue(slider, "1.8")

    expect(container.textContent).toContain("90%")
    expect(onSubmit).not.toHaveBeenCalled()

    finishPointerInteraction(slider)

    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit).toHaveBeenCalledWith({
      provider_preference: "manual_order",
      thinking: true,
      max_output_tokens: 128000,
      temperature: 1.8,
    })

    act(() => root.unmount())
  })

  it("uses a concrete 70% temperature default for roles without an explicit intent value", () => {
    const { container, root } = renderJsx(
      <RoleSettingsPanel
        roleName="graph_agent"
        modelFallbackEnabled={true}
        tokenLimitSummary={{
          context: { knownCount: 0, totalCount: 0, min: null, max: null },
          output: { knownCount: 0, totalCount: 0, min: null, max: null },
        }}
        onModelFallbackChange={vi.fn()}
        onSubmit={vi.fn()}
      />,
    )

    expect(container.textContent).toContain("70%")

    act(() => root.unmount())
  })

  it("can still notify a preview callback from the field-only component", () => {
    const draft: RoleSettingsDraft = {
      providerPreference: "manual_order",
      thinking: true,
      maxOutputTokens: "128000",
      temperature: "0.4",
    }
    const onDraftChange = vi.fn()
    const onDraftPreview = vi.fn()
    const { container, root } = renderJsx(
      <RoleSettingsFields
        roleName="graph_agent"
        modelFallbackEnabled={true}
        draft={draft}
        tokenLimitSummary={{
          context: { knownCount: 0, totalCount: 0, min: null, max: null },
          output: { knownCount: 0, totalCount: 0, min: null, max: null },
        }}
        onModelFallbackChange={vi.fn()}
        onDraftChange={onDraftChange}
        onDraftPreview={onDraftPreview}
      />,
    )

    setInputValue(container.querySelector("[data-role-temperature-input]") as HTMLInputElement, "0.8")

    expect(onDraftChange).not.toHaveBeenCalled()
    expect(onDraftPreview).toHaveBeenCalledWith({
      ...draft,
      temperature: "0.8",
    })

    act(() => root.unmount())
  })
})
