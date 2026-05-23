import { describe, expect, it } from "vitest"
import { buttonVariants } from "./button"

describe("buttonVariants", () => {
  it("uses logical inline padding classes for RTL-compatible icon spacing", () => {
    const classes = buttonVariants({ size: "default" })

    expect(classes).toContain("has-data-[icon=inline-end]:pe-1.5")
    expect(classes).toContain("has-data-[icon=inline-start]:ps-1.5")
    expect(classes).not.toContain("has-data-[icon=inline-end]:pr-1.5")
    expect(classes).not.toContain("has-data-[icon=inline-start]:pl-1.5")
  })
})
