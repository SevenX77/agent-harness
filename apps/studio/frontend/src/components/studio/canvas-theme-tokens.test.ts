import { readFileSync } from "node:fs"
import { describe, expect, it } from "vitest"

const css = readFileSync(new URL("../../index.css", import.meta.url), "utf-8")

function cssVarValue(name: string): string {
  const match = css.match(new RegExp(`${name}:\\s*([^;]+);`))
  if (!match) {
    throw new Error(`Missing CSS variable ${name}`)
  }
  return match[1].trim()
}

describe("Studio canvas theme tokens", () => {
  it("lock canvas chrome to product semantic tokens instead of deriving a new palette", () => {
    const expectedAliases = {
      "--studio-canvas-accent": "var(--primary)",
      "--studio-canvas-accent-muted": "var(--primary)",
      "--studio-canvas-accent-soft": "transparent",
      "--studio-canvas-border": "var(--border)",
      "--studio-canvas-border-soft": "var(--border)",
      "--studio-canvas-surface": "var(--card)",
      "--studio-canvas-surface-elevated": "var(--card)",
      "--studio-canvas-surface-muted": "var(--muted)",
      "--studio-canvas-edge": "var(--border)",
      "--studio-canvas-edge-dot-fill": "var(--background)",
      "--studio-canvas-edge-dot-muted": "var(--muted-foreground)",
    }

    for (const [name, value] of Object.entries(expectedAliases)) {
      expect(cssVarValue(name)).toBe(value)
      expect(cssVarValue(name)).not.toContain("color-mix")
    }
  })
})
