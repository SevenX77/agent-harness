import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { SettingsErrorBoundary } from "./SettingsErrorBoundary"

/**
 * N0 Settings · Shell (atom #9 settings-error-boundary).
 *
 * The boundary wraps every tab so one tab crashing renders a destructive
 * fallback card (+ Retry) instead of a white screen. React error boundaries do
 * not catch during `renderToStaticMarkup` (it re-throws), so the crash → catch
 * → fallback path is exercised by the Playwright e2e; here we lock the two
 * render contracts the boundary owns:
 *   - passthrough: with no error it renders its children verbatim,
 *   - fallback: `getDerivedStateFromError` flips it into a destructive Alert
 *     carrying the tab label, the error message, and a Retry button.
 */
describe("SettingsErrorBoundary", () => {
  it("renders children verbatim when no error has occurred", () => {
    const html = renderToStaticMarkup(
      <SettingsErrorBoundary label="General">
        <div data-probe="ok">healthy tab</div>
      </SettingsErrorBoundary>,
    )
    expect(html).toContain('data-probe="ok"')
    expect(html).toContain("healthy tab")
    expect(html).not.toContain("failed to render")
  })

  it("getDerivedStateFromError captures the thrown error into render state", () => {
    const error = new Error("kaboom")
    expect(SettingsErrorBoundary.getDerivedStateFromError(error)).toEqual({ error })
  })

  it("renders the destructive fallback card with the tab label, message, and Retry once errored", () => {
    // Drive the boundary into its error state, then render its fallback branch
    // directly (SSR cannot trigger the catch, so we set state explicitly).
    const boundary = new SettingsErrorBoundary({
      label: "API Keys",
      children: <div>never shown</div>,
    })
    boundary.state = { error: new Error("provider list exploded") }

    const html = renderToStaticMarkup(<>{boundary.render()}</>)
    expect(html).toContain("API Keys failed to render")
    expect(html).toContain("provider list exploded")
    expect(html).toContain("Retry")
    expect(html).not.toContain("never shown")
  })
})
