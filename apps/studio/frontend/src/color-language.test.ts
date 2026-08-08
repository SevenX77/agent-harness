/**
 * Guards the two rules of Studio's colour language.
 *
 * Decision: docs/design/2026-08-08-studio-color-language-and-trace-density-decision.md
 * Spec: docs/development/FRONTEND_UI_SPEC.md §2.2
 *
 * 1. `--primary` is a FILL, not a text colour. Measured on the running desktop
 *    app it renders rgb(55,42,172) on a rgb(23,23,23) card — 1.78:1, below even
 *    the 3:1 large-text floor. Anything that needs to read as brand-coloured
 *    text uses `--link`, which is the same hue lifted into readable range.
 * 2. Every token this app is allowed to paint text with clears WCAG AA (4.5:1)
 *    against `--card` in the dark theme — the theme the product actually ships
 *    (FRONTEND_UI_SPEC §2.3 "Dark Theme Only").
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC_DIR = fileURLToPath(new URL('.', import.meta.url))
const CSS = readFileSync(join(SRC_DIR, 'index.css'), 'utf-8')

/** Tokens business code may hand to a `text-*` utility. */
const TEXT_SAFE_TOKENS = [
  '--foreground',
  '--muted-foreground',
  '--link',
  '--success',
  '--warning',
  '--destructive',
] as const

/** WCAG 2.x AA for normal-size text. */
const AA_NORMAL_TEXT = 4.5

function darkThemeToken(name: string): string {
  // `.dark { … }` is the last block that declares these tokens; the product
  // ships dark, so that is the value worth asserting on.
  const declarations = [...CSS.matchAll(new RegExp(`${name}:\\s*([^;]+);`, 'g'))]
  if (declarations.length === 0) throw new Error(`Missing CSS variable ${name}`)
  return declarations[declarations.length - 1][1].trim()
}

/** oklch(L C H) → linear sRGB, per the Oklab reference implementation. */
function oklchToLinearRgb(value: string): [number, number, number] {
  const match = value.match(/oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)/)
  if (!match) throw new Error(`Not an oklch colour: ${value}`)
  const [lightness, chroma, hueDegrees] = match.slice(1, 4).map(Number)
  const hue = (hueDegrees * Math.PI) / 180
  const a = chroma * Math.cos(hue)
  const b = chroma * Math.sin(hue)

  const l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s = (lightness - 0.0894841775 * a - 1.291485548 * b) ** 3

  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ]
}

function relativeLuminance(token: string): number {
  const [r, g, b] = oklchToLinearRgb(darkThemeToken(token)).map((channel) =>
    Math.min(1, Math.max(0, channel)),
  )
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrastAgainstCard(token: string): number {
  const [brighter, darker] = [relativeLuminance(token), relativeLuminance('--card')].sort(
    (left, right) => right - left,
  )
  return (brighter + 0.05) / (darker + 0.05)
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) return sourceFiles(path)
    return /\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry) ? [path] : []
  })
}

describe('Studio colour language', () => {
  it('never paints text with --primary, which is a fill colour', () => {
    // `text-primary-foreground` (white ON primary) is the correct pairing and
    // must keep working, so the guard stops at a bare `text-primary`.
    const barePrimaryText = /\btext-primary\b(?!-)/
    const offenders = sourceFiles(SRC_DIR)
      .filter((path) => barePrimaryText.test(readFileSync(path, 'utf-8')))
      .map((path) => path.slice(SRC_DIR.length).replace(/\\/g, '/'))

    expect(offenders).toEqual([])
  })

  it('keeps every text-safe token above WCAG AA against --card in the dark theme', () => {
    const failures = TEXT_SAFE_TOKENS.map((token) => ({
      token,
      contrast: Number(contrastAgainstCard(token).toFixed(2)),
    })).filter((entry) => entry.contrast < AA_NORMAL_TEXT)

    expect(failures).toEqual([])
  })

  it('proves --primary would fail that bar, so the ban is measured and not taste', () => {
    expect(contrastAgainstCard('--primary')).toBeLessThan(3)
  })

  it('derives --link from the --primary hue so the brand survives the lift', () => {
    const hue = (token: string) => Number(darkThemeToken(token).match(/oklch\([\d.]+ [\d.]+ ([\d.]+)/)![1])
    expect(hue('--link')).toBeCloseTo(hue('--primary'), 0)
  })
})
