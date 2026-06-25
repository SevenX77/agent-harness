import { describe, expect, it } from "vitest"
import {
  DEFAULT_TOOLTIP_DELAY_MS,
  tooltipContentBaseClassName,
} from "./tooltip"

describe("Tooltip", () => {
  it("uses a 500ms hover delay by default", () => {
    expect(DEFAULT_TOOLTIP_DELAY_MS).toBe(500)
  })

  it("keeps long tooltip text inside the viewport and wraps unbroken diagnostics", () => {
    expect(tooltipContentBaseClassName).toContain("max-w-[min(32rem,calc(100vw-2rem))]")
    expect(tooltipContentBaseClassName).toContain("overflow-hidden")
    expect(tooltipContentBaseClassName).toContain("whitespace-normal")
    expect(tooltipContentBaseClassName).toContain("[overflow-wrap:anywhere]")
  })
})
