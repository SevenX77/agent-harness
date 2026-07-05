// @vitest-environment jsdom
import { act, type InputHTMLAttributes, type ReactNode } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, describe, expect, it, vi } from "vitest"
import { RoleSettingsFields, type RoleSettingsDraft } from "./RoleSettingsDialog"

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

describe("RoleSettingsFields behavior", () => {
  afterEach(() => {
    document.body.innerHTML = ""
    vi.clearAllMocks()
  })

  it("updates the parent draft immediately when the temperature slider moves", () => {
    const draft: RoleSettingsDraft = {
      providerPreference: "manual_order",
      thinking: true,
      maxOutputTokens: "128000",
      temperature: "0.4",
    }
    const onDraftChange = vi.fn()
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
      />,
    )

    setInputValue(container.querySelector("[data-role-temperature-input]") as HTMLInputElement, "0.8")

    expect(onDraftChange).toHaveBeenCalledWith({
      ...draft,
      temperature: "0.8",
    })

    act(() => root.unmount())
  })
})
