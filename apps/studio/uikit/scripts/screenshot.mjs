/**
 * Take a viewport screenshot of the dev server in light + dark mode.
 *
 * Usage (from apps/studio/uikit/):
 *   node scripts/screenshot.mjs
 *   PORT=5173 node scripts/screenshot.mjs
 *   URL=http://host:1234 node scripts/screenshot.mjs
 *
 * Outputs:
 *   /tmp/uikit-light.png
 *   /tmp/uikit-dark.png
 */
import { chromium } from "playwright-chromium"

const url = process.env.URL ?? `http://localhost:${process.env.PORT ?? 55424}/`

const browser = await chromium.launch({ args: ["--no-sandbox"] })

for (const mode of ["light", "dark"]) {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: mode,
  })
  const page = await ctx.newPage()
  await page.goto(url, { waitUntil: "networkidle", timeout: 15000 })
  // Force the chosen theme regardless of localStorage state from previous runs.
  await page.evaluate((m) => {
    localStorage.setItem("theme", m)
    document.documentElement.classList.remove("light", "dark")
    document.documentElement.classList.add(m)
  }, mode)
  await page.waitForTimeout(150)
  const path = `/tmp/uikit-${mode}.png`
  await page.screenshot({ path, fullPage: false })
  console.log(`saved ${path}`)
  await ctx.close()
}

await browser.close()
