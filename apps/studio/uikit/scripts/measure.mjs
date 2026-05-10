import { chromium } from "playwright-chromium"

const url = process.env.URL ?? `http://localhost:${process.env.PORT ?? 55424}/`

const browser = await chromium.launch({ args: ["--no-sandbox"] })
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await ctx.newPage()
await page.goto(url, { waitUntil: "networkidle", timeout: 15000 })

const measurements = await page.evaluate(() => {
  const out = {}
  const sel = (s) => {
    const el = document.querySelector(s)
    if (!el) return null
    const r = el.getBoundingClientRect()
    return {
      tag: el.tagName,
      class: (el.className || "").toString().slice(0, 80),
      width: Math.round(r.width),
      height: Math.round(r.height),
      style: el.getAttribute("style"),
    }
  }
  out.body = sel("body")
  out.toolbar = sel('[class*="w-12"][class*="bg-sidebar"]')
  out.group = sel('[data-slot="resizable-panel-group"]')
  out.panels = []
  document
    .querySelectorAll('[data-slot="resizable-panel"]')
    .forEach((el) => {
      const r = el.getBoundingClientRect()
      out.panels.push({
        id: el.getAttribute("data-panel-id") ?? el.id ?? "?",
        width: Math.round(r.width),
        style: el.getAttribute("style"),
        class: (el.className || "").toString().slice(0, 60),
      })
    })
  return out
})

console.log(JSON.stringify(measurements, null, 2))

await browser.close()
