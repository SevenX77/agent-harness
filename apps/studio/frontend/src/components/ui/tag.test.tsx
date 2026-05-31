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

  it("keeps semantic entity tag variants on the shared success-tinted background", () => {
    const warningClasses = tagVariants({ variant: "warning" }).split(/\s+/)
    const destructiveClasses = tagVariants({ variant: "destructive" }).split(/\s+/)
    const probeVerifiedClasses = tagVariants({ variant: "probe-verified" }).split(/\s+/)

    expect(warningClasses).toContain("border-warning")
    expect(warningClasses).toContain("bg-success/10")
    expect(warningClasses).toContain("text-foreground")
    expect(warningClasses).not.toContain("bg-warning-background")

    expect(destructiveClasses).toContain("border-tag-destructive-border")
    expect(destructiveClasses).toContain("bg-success/10")
    expect(destructiveClasses).toContain("text-foreground")
    expect(destructiveClasses).not.toContain("bg-destructive-background")

    expect(probeVerifiedClasses).toContain("border-multimodal-border")
    expect(probeVerifiedClasses).toContain("bg-success/10")
    expect(probeVerifiedClasses).toContain("text-foreground")
    expect(probeVerifiedClasses).not.toContain("border-warning")
  })
})
