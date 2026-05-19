/**
 * Headless-browser diagnosis for the dev server.
 *
 * Loads http://localhost:<PORT> in Chromium (Playwright), captures all console
 * messages, page errors, failed requests, and a snippet of the rendered #root
 * HTML. Used to confirm whether the page actually rendered, and to surface
 * runtime errors that you would otherwise only see in DevTools.
 *
 * Usage (from apps/studio/uikit/):
 *   node scripts/diag.mjs                 # default http://localhost:55424
 *   PORT=5173 node scripts/diag.mjs       # override port
 *   URL=http://host:1234 node scripts/diag.mjs
 */
import { chromium } from "playwright-chromium"

const url = process.env.URL ?? `http://localhost:${process.env.PORT ?? 55424}/`

const browser = await chromium.launch({ args: ["--no-sandbox"] })
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await ctx.newPage()

const logs = []
const errors = []

page.on("console", (msg) => {
  logs.push(`[${msg.type()}] ${msg.text()}`)
})
page.on("pageerror", (err) => {
  errors.push(`[pageerror] ${err.message}\n${err.stack ?? ""}`)
})
page.on("requestfailed", (req) => {
  errors.push(`[requestfailed] ${req.url()} -> ${req.failure()?.errorText}`)
})

try {
  await page.goto(url, { waitUntil: "networkidle", timeout: 15000 })
} catch (e) {
  errors.push(`[nav] ${e.message}`)
}

const root = await page
  .$eval("#root", (el) => el.outerHTML.slice(0, 800))
  .catch((e) => `<read err: ${e.message}>`)

console.log(`=== TARGET: ${url} ===`)
console.log("\n=== ROOT (first 800 chars) ===")
console.log(root)
console.log("\n=== CONSOLE ===")
for (const l of logs) console.log(l)
console.log("\n=== ERRORS ===")
if (errors.length === 0) {
  console.log("(none)")
} else {
  for (const e of errors) console.log(e)
}

await browser.close()
process.exit(errors.length === 0 ? 0 : 1)
