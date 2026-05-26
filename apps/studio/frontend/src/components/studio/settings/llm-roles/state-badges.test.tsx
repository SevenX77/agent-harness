import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { CoolingDownCountdown, formatCoolingDownRemaining } from "./cooling-down-countdown"
import { ProviderStateBadge } from "./provider-state-badge"
import { RoleFitBadge } from "./role-fit-badge"

describe("LLM role state badges", () => {
  it("renders exactly the five provider state labels", () => {
    const html = renderToStaticMarkup(
      <>
        <ProviderStateBadge state="ready" />
        <ProviderStateBadge state="untested" />
        <ProviderStateBadge state="cooling_down" retryAt="2026-05-26T18:30:00Z" />
        <ProviderStateBadge state="needs_setup" reasonCode="invalid_model" detail="Model does not exist." />
        <ProviderStateBadge state="off" />
      </>,
    )

    expect(html).toContain("Ready")
    expect(html).toContain("Untested")
    expect(html).toContain("Cooling Down")
    expect(html).toContain("Needs Setup")
    expect(html).toContain("Off")
    expect(html).toContain('data-provider-state-label="needs_setup"')
    expect(html).not.toContain(">invalid_model<")
  })

  it("renders exactly the four role fit labels", () => {
    const html = renderToStaticMarkup(
      <>
        <RoleFitBadge fit="using" />
        <RoleFitBadge fit="downgraded" />
        <RoleFitBadge fit="needs_test" />
        <RoleFitBadge fit="not_fit" />
      </>,
    )

    expect(html).toContain("Using")
    expect(html).toContain("Downgraded")
    expect(html).toContain("Needs Test")
    expect(html).toContain("Not Fit")
  })

  it("formats Cooling Down countdowns and exposes a Test Now action", () => {
    const now = new Date("2026-05-26T18:28:55Z")
    const retryAt = "2026-05-26T18:30:00Z"
    const html = renderToStaticMarkup(
      <CoolingDownCountdown
        retryAt={retryAt}
        now={now}
        onTestNow={() => undefined}
      />,
    )

    expect(formatCoolingDownRemaining(retryAt, now)).toBe("1m 5s")
    expect(html).toContain("1m 5s")
    expect(html).toContain("Test Now")
    expect(html).not.toContain("route")
    expect(html).not.toContain("endpoint")
    expect(html).not.toContain("canonical")
  })
})
