import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import {
  CatalogAccordion,
  CatalogAccordionContent,
  CatalogAccordionItem,
  CatalogAccordionTrigger,
} from "./catalog-accordion"

describe("CatalogAccordion", () => {
  it("renders categorized sections with expanded/collapsed state icons before the title", () => {
    const html = renderToStaticMarkup(
      <CatalogAccordion type="single" value="providers">
        <CatalogAccordionItem value="providers">
          <CatalogAccordionTrigger>
            <span>Official Providers</span>
          </CatalogAccordionTrigger>
          <CatalogAccordionContent>
            <div>Provider cards</div>
          </CatalogAccordionContent>
        </CatalogAccordionItem>
      </CatalogAccordion>,
    )

    expect(html).toContain('data-slot="catalog-accordion"')
    expect(html).toContain('data-slot="catalog-accordion-trigger"')
    expect(html).toContain('data-slot="catalog-accordion-state-icon"')
    expect(html.indexOf("catalog-accordion-state-icon")).toBeLessThan(html.indexOf("Official Providers"))
    expect(html).toContain("lucide-chevron-right")
    expect(html).toContain("lucide-chevron-down")
    expect(html).not.toContain("lucide-chevron-up")
    expect(html).not.toContain("h-(--radix-accordion-content-height)")
  })
})
