import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { ScrollArea } from "./scroll-area"

describe("ScrollArea", () => {
  it("clips native scrollbars so panels use the shadcn scrollbar surface", () => {
    const html = renderToStaticMarkup(
      <ScrollArea>
        <div>Scrollable content</div>
      </ScrollArea>,
    )

    expect(html).toContain("overflow-hidden")
    expect(html).toContain("min-h-0")
    expect(html).toContain("scrollbar-width:none")
    expect(html).toContain("&amp;::-webkit-scrollbar")
  })
})
