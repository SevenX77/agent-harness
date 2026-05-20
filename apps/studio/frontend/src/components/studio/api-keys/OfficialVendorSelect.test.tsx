import { isValidElement, type ReactElement, type ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { OFFICIAL_VENDORS, OfficialVendorSelect } from "./OfficialVendorSelect"

function textOf(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") {
    return ""
  }
  if (typeof node === "string" || typeof node === "number") {
    return String(node)
  }
  if (Array.isArray(node)) {
    return node.map(textOf).join("")
  }
  if (isValidElement(node)) {
    return textOf((node as ReactElement<{ children?: ReactNode }>).props.children)
  }
  return ""
}

describe("OfficialVendorSelect", () => {
  it("renders 5 official vendors in dropdown content", () => {
    const element = OfficialVendorSelect({ value: "", onChange: vi.fn() })
    const text = textOf(element)

    expect(OFFICIAL_VENDORS).toHaveLength(5)
    for (const vendor of OFFICIAL_VENDORS) {
      expect(text).toContain(vendor.label)
    }
  })

  it("calls onChange with the full vendor object on selection", () => {
    const onChange = vi.fn()
    const element = OfficialVendorSelect({ value: "", onChange })

    ;(element.props.onValueChange as (code: string) => void)("anthropic")

    expect(onChange).toHaveBeenCalledWith({
      code: "anthropic",
      label: "Anthropic",
      baseUrl: "https://api.anthropic.com",
    })
  })
})
