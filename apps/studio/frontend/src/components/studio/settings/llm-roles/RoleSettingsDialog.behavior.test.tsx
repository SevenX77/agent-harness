// @vitest-environment jsdom
import { act, type InputHTMLAttributes, type ReactNode } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, describe, expect, it, vi } from "vitest"
import { PROVIDER_DEFAULT_EFFORT } from "@/components/studio/llm-effort"
import { RoleSettingsFields, RoleSettingsPanel, type RoleSettingsDraft } from "./RoleSettingsDialog"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

vi.mock("@/components/ui/select", () => ({
  Select: ({ value, onValueChange, disabled, children }: {
    value: string
    onValueChange?: (value: string) => void
    disabled?: boolean
    children: ReactNode
  }) => (
    <select
      data-role-effort-input="true"
      disabled={disabled}
      value={value}
      onChange={(event) => onValueChange?.(event.currentTarget.value)}
    >
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
  SelectValue: () => null,
  SelectContent: ({ children }: { children: ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children: ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}))

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
        effortLevels={[]}
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
      reasoning_effort: null,
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
        effortLevels={[]}
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
      reasoning_effort: null,
    })

    act(() => root.unmount())
  })

  it("uses a concrete 70% temperature default for roles without an explicit intent value", () => {
    const { container, root } = renderJsx(
      <RoleSettingsPanel
        roleName="graph_agent"
        modelFallbackEnabled={true}
        effortLevels={[]}
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
      reasoningEffort: PROVIDER_DEFAULT_EFFORT,
    }
    const onDraftChange = vi.fn()
    const onDraftPreview = vi.fn()
    const { container, root } = renderJsx(
      <RoleSettingsFields
        roleName="graph_agent"
        modelFallbackEnabled={true}
        draft={draft}
        effortLevels={[]}
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

describe("role effort control", () => {
  afterEach(() => {
    document.body.innerHTML = ""
    vi.clearAllMocks()
  })

  it("offers the levels the role's models sell and submits the chosen one", () => {
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
        effortLevels={["low", "high", "max"]}
        tokenLimitSummary={{
          context: { knownCount: 0, totalCount: 0, min: null, max: null },
          output: { knownCount: 0, totalCount: 0, min: null, max: null },
        }}
        onModelFallbackChange={vi.fn()}
        onSubmit={onSubmit}
      />,
    )

    const effort = container.querySelector("[data-role-effort-input]") as HTMLSelectElement
    expect([...effort.options].map((option) => option.value)).toEqual([
      PROVIDER_DEFAULT_EFFORT, "low", "high", "max",
    ])

    act(() => {
      effort.value = "high"
      effort.dispatchEvent(new Event("change", { bubbles: true }))
    })

    expect(onSubmit).toHaveBeenCalledWith({
      provider_preference: "manual_order",
      thinking: true,
      max_output_tokens: 128000,
      temperature: 1.4,
      reasoning_effort: "high",
    })

    act(() => root.unmount())
  })

  it("goes back to the provider default when the choice is cleared", () => {
    const onSubmit = vi.fn()
    const { container, root } = renderJsx(
      <RoleSettingsPanel
        roleName="graph_agent"
        modelFallbackEnabled={true}
        intent={{
          provider_preference: "manual_order",
          thinking: false,
          max_output_tokens: null,
          temperature: 1.4,
          reasoning_effort: "high",
        }}
        effortLevels={["low", "high"]}
        tokenLimitSummary={{
          context: { knownCount: 0, totalCount: 0, min: null, max: null },
          output: { knownCount: 0, totalCount: 0, min: null, max: null },
        }}
        onModelFallbackChange={vi.fn()}
        onSubmit={onSubmit}
      />,
    )

    const effort = container.querySelector("[data-role-effort-input]") as HTMLSelectElement
    expect(effort.value).toBe("high")

    act(() => {
      effort.value = PROVIDER_DEFAULT_EFFORT
      effort.dispatchEvent(new Event("change", { bubbles: true }))
    })

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ reasoning_effort: null }))

    act(() => root.unmount())
  })

  it("says nothing was reported rather than offering a level no model claims", () => {
    const { container, root } = renderJsx(
      <RoleSettingsPanel
        roleName="graph_agent"
        modelFallbackEnabled={true}
        effortLevels={[]}
        tokenLimitSummary={{
          context: { knownCount: 0, totalCount: 0, min: null, max: null },
          output: { knownCount: 0, totalCount: 0, min: null, max: null },
        }}
        onModelFallbackChange={vi.fn()}
        onSubmit={vi.fn()}
      />,
    )

    const effort = container.querySelector("[data-role-effort-input]") as HTMLSelectElement
    expect(effort.disabled).toBe(true)
    expect([...effort.options].map((option) => option.value)).toEqual([PROVIDER_DEFAULT_EFFORT])

    act(() => root.unmount())
  })
})
