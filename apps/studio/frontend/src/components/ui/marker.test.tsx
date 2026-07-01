import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { Marker, MarkerContent, MarkerIcon } from "./marker"

describe("Marker", () => {
  it("renders an inline conversation marker", () => {
    const html = renderToStaticMarkup(
      <Marker>
        <MarkerIcon>*</MarkerIcon>
        <MarkerContent>Thinking...</MarkerContent>
      </Marker>,
    )

    expect(html).toContain('data-slot="marker"')
    expect(html).toContain('data-slot="marker-icon"')
    expect(html).toContain('data-slot="marker-content"')
    expect(html).toContain("Thinking...")
  })

  it("supports separator and asChild variants", () => {
    const html = renderToStaticMarkup(
      <Marker variant="separator" asChild>
        <button type="button">
          <MarkerContent>Today</MarkerContent>
        </button>
      </Marker>,
    )

    expect(html).toContain("<button")
    expect(html).toContain('data-variant="separator"')
    expect(html).toContain("Today")
  })
})
