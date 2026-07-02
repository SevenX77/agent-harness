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
      // shadcn card convention: a resting surface separates via a crisp
      // foreground-tinted ring, not the raw --border token — see
      // --surface-outline below.
      "--studio-canvas-border": "var(--surface-outline)",
      "--studio-canvas-border-soft": "var(--surface-outline)",
      "--studio-canvas-surface": "var(--card)",
      "--studio-canvas-surface-elevated": "var(--card)",
      "--studio-canvas-surface-muted": "var(--muted)",
      // Light needs a stronger edge line than the near-invisible light --border;
      // --ring is the semantic mid-gray. .dark overrides back to var(--border).
      "--studio-canvas-edge": "var(--ring)",
      "--studio-canvas-edge-dot-fill": "var(--background)",
      "--studio-canvas-edge-dot-muted": "var(--muted-foreground)",
    }

    for (const [name, value] of Object.entries(expectedAliases)) {
      expect(cssVarValue(name)).toBe(value)
      expect(cssVarValue(name)).not.toContain("color-mix")
    }
  })

  it("derives --surface-outline from --foreground so it self-adapts across themes without a .dark override", () => {
    // oklab(<foreground> / 10%) is exactly shadcn's own Card ring formula —
    // it reduces to a black/10% ring in light and a white/10% ring in dark
    // (matching the theme's existing --border) from ONE declaration.
    expect(cssVarValue("--surface-outline")).toBe("color-mix(in oklab, var(--foreground) 10%, transparent)")
  })

  it("keeps chrome shadows on the semantic --shadow-* scale, never a literal box-shadow value", () => {
    for (const name of ["--studio-shadow-overlay", "--studio-shadow-toolbar", "--studio-shadow-minimap", "--studio-shadow-frame"]) {
      const value = cssVarValue(name)
      expect(value.startsWith("var(--shadow-")).toBe(true)
    }
    // The docked copilot panel is border-only chrome (shadcn Sidebar
    // convention) — no elevation shadow in either theme.
    expect(cssVarValue("--studio-shadow-panel")).toBe("none")
  })
})
