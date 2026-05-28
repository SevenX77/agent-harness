import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { Tag, tagVariants } from "./tag"

describe("Tag", () => {
  it("renders the reusable rounded outline style for provider/model labels", () => {
    const html = renderToStaticMarkup(
      <Tag variant="success" size="sm">
        OpenRouter
      </Tag>,
    )

    expect(html).toContain('data-slot="tag"')
    expect(html).toContain('data-variant="success"')
    expect(html).toContain('data-size="sm"')
    expect(html).toContain("rounded-full")
    expect(html).toContain("border-success")
    expect(html).toContain("bg-success/10")
    expect(html).toContain("OpenRouter")
  })
})

describe("tagVariants", () => {
  it("keeps status badge colors out of the default entity tag style", () => {
    const classes = tagVariants({ variant: "default" })

    expect(classes).toContain("border-border")
    expect(classes).toContain("bg-muted/20")
    expect(classes).not.toContain("border-success")
    expect(classes).not.toContain("bg-success/10")
  })
})
