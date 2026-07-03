import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { ErrorBoundary } from "./ErrorBoundary"

/**
 * App-wide render boundary: any exception thrown while rendering children is
 * caught and shown as a fallback card, so a malformed edit can never black-screen
 * Studio. React boundaries do not catch during `renderToStaticMarkup` (it
 * re-throws), so the live crash→catch path is exercised by e2e; here we lock the
 * two render contracts the boundary owns.
 */
describe("ErrorBoundary", () => {
  it("renders children verbatim when no error has occurred", () => {
    const html = renderToStaticMarkup(
      <ErrorBoundary label="Studio">
        <div data-probe="ok">healthy</div>
      </ErrorBoundary>,
    )
    expect(html).toContain('data-probe="ok"')
    expect(html).toContain("healthy")
    expect(html).not.toContain("failed to render")
  })

  it("getDerivedStateFromError captures the thrown error into render state", () => {
    const error = new Error("kaboom")
    expect(ErrorBoundary.getDerivedStateFromError(error)).toEqual({ error })
  })

  it("renders the destructive fallback card with the label, message, and Retry once errored", () => {
    const boundary = new ErrorBoundary({ label: "Studio", children: <div>never shown</div> })
    boundary.state = { error: new Error("io panel exploded") }

    const html = renderToStaticMarkup(<>{boundary.render()}</>)
    expect(html).toContain("Studio failed to render")
    expect(html).toContain("io panel exploded")
    expect(html).toContain("Retry")
    expect(html).not.toContain("never shown")
  })
})
