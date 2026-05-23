import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { Accordion, AccordionContent, AccordionItem } from "./accordion"

describe("AccordionContent", () => {
  it("does not lock the inner content to the initial Radix measured height", () => {
    const html = renderToStaticMarkup(
      <Accordion type="single" value="item">
        <AccordionItem value="item">
          <AccordionContent>
            <div>Async result content</div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>,
    )

    expect(html).toContain('data-slot="accordion-content"')
    expect(html).not.toContain("h-(--radix-accordion-content-height)")
    expect(html).not.toContain("height:var(--radix-accordion-content-height)")
  })
})
