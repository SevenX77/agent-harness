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

  it("uses matching tinted backgrounds for every semantic entity tag", () => {
    const infoClasses = tagVariants({ variant: "info" }).split(/\s+/)
    const successClasses = tagVariants({ variant: "success" }).split(/\s+/)
    const warningClasses = tagVariants({ variant: "warning" }).split(/\s+/)
    const destructiveClasses = tagVariants({ variant: "destructive" }).split(/\s+/)
    const probeVerifiedClasses = tagVariants({ variant: "probe-verified" }).split(/\s+/)

    expect(infoClasses).toEqual(expect.arrayContaining(["border-primary/70", "bg-primary/10"]))
    expect(successClasses).toEqual(expect.arrayContaining(["border-success", "bg-success/10"]))
    expect(warningClasses).toContain("border-warning")
    expect(warningClasses).toContain("bg-warning/10")
    expect(warningClasses).toContain("text-foreground")

    expect(destructiveClasses).toContain("border-tag-destructive-border")
    expect(destructiveClasses).toContain("bg-tag-destructive-border/10")
    expect(destructiveClasses).toContain("text-foreground")

    expect(probeVerifiedClasses).toContain("border-multimodal-border")
    expect(probeVerifiedClasses).toContain("bg-multimodal-border/10")
    expect(probeVerifiedClasses).toContain("text-foreground")
    expect(probeVerifiedClasses).not.toContain("bg-success/10")
    expect(probeVerifiedClasses).not.toContain("border-warning")
  })
})
