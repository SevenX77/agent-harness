/**
 * Capture shadcn baselines (radix-mira preset has no live component preview
 * page, but shadcn ui.shadcn.com itself shows canonical density / typography
 * / radii / icon weights). Output to /tmp/shadcn-*.png so a2 (Gemini) can be
 * pointed at them — Gemini fetches URLs herself, but humans (and master) can
 * also eyeball these.
 */
import { chromium } from "playwright-chromium"
import { mkdir } from "node:fs/promises"

const targets = [
  ["create", "https://ui.shadcn.com/create?preset=b38miVIYq&template=vite&pointer=true&rtl=true"],
  ["dashboard", "https://ui.shadcn.com/blocks/dashboard"],
  ["sidebar", "https://ui.shadcn.com/blocks/sidebar"],
  ["docs-button", "https://ui.shadcn.com/docs/components/button"],
  ["docs-dropdown", "https://ui.shadcn.com/docs/components/dropdown-menu"],
  ["docs-dialog", "https://ui.shadcn.com/docs/components/dialog"],
  ["docs-resizable", "https://ui.shadcn.com/docs/components/resizable"],
  ["docs-sidebar", "https://ui.shadcn.com/docs/components/sidebar"],
]

await mkdir("/tmp/shadcn-baseline", { recursive: true })

const browser = await chromium.launch({ args: ["--no-sandbox"] })

for (const [name, url] of targets) {
  for (const mode of ["light", "dark"]) {
    const ctx = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      colorScheme: mode,
    })
    const page = await ctx.newPage()
    try {
      await page.goto(url, { waitUntil: "networkidle", timeout: 30000 })
      await page.waitForTimeout(600)
      const path = `/tmp/shadcn-baseline/${name}-${mode}.png`
      await page.screenshot({ path, fullPage: false })
      console.log(`saved ${path}`)
    } catch (e) {
      console.log(`SKIP ${name} ${mode}: ${e.message}`)
    }
    await ctx.close()
  }
}

await browser.close()
