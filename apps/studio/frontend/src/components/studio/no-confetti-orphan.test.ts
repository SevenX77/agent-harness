/// <reference types="node" />

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const FRONTEND_SRC_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..")
const REMOVED_CONFETTI_ORPHANS = [
  "lib/confetti.ts",
  "types/canvas-confetti.d.ts",
] as const

function walkSourceFiles(root: string): string[] {
  const entries = readdirSync(root)
  return entries.flatMap((entry: string) => {
    const fullPath = path.join(root, entry)
    const stats = statSync(fullPath)
    if (stats.isDirectory()) {
      return walkSourceFiles(fullPath)
    }
    // Test files legitimately mention the orphan paths/strings in their own
    // assertions (e.g. this file). Only PRODUCTION sources must be confetti-free.
    if (fullPath.endsWith(".test.ts") || fullPath.endsWith(".test.tsx")) {
      return []
    }
    return fullPath.endsWith(".ts") || fullPath.endsWith(".tsx") ? [fullPath] : []
  })
}

describe("n6 publish no-virtual-requirements (confetti orphan cleanup)", () => {
  it("removes the orphan confetti source and type-declaration files", () => {
    for (const relativePath of REMOVED_CONFETTI_ORPHANS) {
      expect(existsSync(path.join(FRONTEND_SRC_ROOT, relativePath))).toBe(false)
    }
  })

  it("keeps the frontend source tree free of any confetti import or reference", () => {
    const sourceFiles = walkSourceFiles(FRONTEND_SRC_ROOT)

    for (const filePath of sourceFiles) {
      const source = readFileSync(filePath, "utf-8")
      expect(source).not.toMatch(/canvas-confetti/)
      expect(source).not.toMatch(/\bcelebrateSuccess\b/)
    }
  })
})
