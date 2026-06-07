import { readFileSync } from "node:fs"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { SaveStatusBadge } from "./save-status-badge"

describe("SaveStatusBadge", () => {
  it("does not render the idle state", () => {
    expect(renderToStaticMarkup(<SaveStatusBadge status="idle" />)).toBe("")
  })

  it.each([
    ["pending", "Pending"],
    ["saving", "Saving"],
    ["saved", "Saved"],
    ["error", "Save failed"],
  ] as const)("renders accessible %s status feedback", (status, label) => {
    const html = renderToStaticMarkup(<SaveStatusBadge status={status} />)

    expect(html).toContain('data-slot="badge"')
    expect(html).toContain('data-save-status-badge="true"')
    expect(html).toContain(`data-save-status="${status}"`)
    expect(html).toContain(`aria-label="${label}"`)
    expect(html).toContain('data-save-status-icon="true"')
    expect(html).toContain(label)
  })

  it("uses local design-system primitives and no one-off color classes", () => {
    const source = readFileSync(new URL("./save-status-badge.tsx", import.meta.url), "utf8")

    expect(source).toContain('from "@/components/ui/badge"')
    expect(source).toContain('from "lucide-react"')
    expect(source).not.toMatch(/#[0-9a-fA-F]{3,8}/)
    expect(source).not.toMatch(/\b(?:bg|text|border|ring)-(?:gray|slate|zinc|red|green|blue|yellow|purple|orange|amber|emerald)-\d{2,3}\b/)
  })
})
