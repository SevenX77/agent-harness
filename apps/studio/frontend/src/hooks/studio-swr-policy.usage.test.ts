import { describe, expect, it } from "vitest"
import { readdirSync, readFileSync, statSync } from "node:fs"
import path from "node:path"

const SRC_ROOT = path.join(process.cwd(), "src")

function productionSourceFiles(dir: string): string[] {
  const entries = readdirSync(dir)
  return entries.flatMap((entry) => {
    const absolute = path.join(dir, entry)
    const stats = statSync(absolute)
    if (stats.isDirectory()) {
      if (entry === "testing") return []
      return productionSourceFiles(absolute)
    }
    if (!/\.(ts|tsx)$/.test(entry)) return []
    if (entry.includes(".test.")) return []
    return [absolute]
  })
}

function findUseSWRCallStarts(source: string): number[] {
  const starts: number[] = []
  const callStart = /\buseSWR(?:<[^>]+>)?\s*\(/g
  for (let match = callStart.exec(source); match; match = callStart.exec(source)) {
    starts.push(match.index)
  }
  return starts
}

function callExpressionAt(source: string, start: number): string {
  const open = source.indexOf("(", start)
  if (open === -1) return source.slice(start)

  let depth = 0
  let quote: "'" | '"' | "`" | null = null
  let escaped = false
  for (let index = open; index < source.length; index += 1) {
    const char = source[index]
    if (quote) {
      if (escaped) {
        escaped = false
      } else if (char === "\\") {
        escaped = true
      } else if (char === quote) {
        quote = null
      }
      continue
    }

    if (char === "'" || char === '"' || char === "`") {
      quote = char
      continue
    }
    if (char === "(") {
      depth += 1
      continue
    }
    if (char === ")") {
      depth -= 1
      if (depth === 0) {
        return source.slice(start, index + 1)
      }
    }
  }
  return source.slice(start)
}

describe("Studio SWR truth-read policy usage", () => {
  it("requires every production useSWR read to opt into the Studio truth policy", () => {
    const offenders = productionSourceFiles(SRC_ROOT).flatMap((file) => {
      const source = readFileSync(file, "utf-8")
      return findUseSWRCallStarts(source)
        .map((start) => callExpressionAt(source, start))
        .filter((call) => !call.includes("STUDIO_TRUTH_SWR_CONFIG"))
        .map((call) => {
          const relative = path.relative(process.cwd(), file).replaceAll("\\", "/")
          return `${relative}: ${call.split("\n")[0]}`
        })
    })

    expect(offenders).toEqual([])
  })
})
