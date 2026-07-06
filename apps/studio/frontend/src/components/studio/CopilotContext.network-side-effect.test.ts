// @vitest-environment node
import { readFileSync, readdirSync } from "node:fs"
import { join, relative } from "node:path"
import { describe, expect, it } from "vitest"

const FRONTEND_SRC_ROOT = join(__dirname, "..", "..")
const FORBIDDEN_ENDPOINT = "/copilot" + "/context"
const FORBIDDEN_HOOK = "use" + "CopilotContext"

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) {
      return sourceFiles(path)
    }
    if (!/\.(ts|tsx)$/.test(entry.name) || /\.test\.(ts|tsx)$/.test(entry.name)) {
      return []
    }
    return [path]
  })
}

describe("Copilot automatic context network guard", () => {
  it("does not keep a frontend channel that posts canvas/UI selection into Copilot context", () => {
    const offenders = sourceFiles(FRONTEND_SRC_ROOT)
      .map((path) => ({
        path: relative(FRONTEND_SRC_ROOT, path),
        source: readFileSync(path, "utf8"),
      }))
      .filter(({ source }) => source.includes(FORBIDDEN_ENDPOINT) || source.includes(FORBIDDEN_HOOK))
      .map(({ path }) => path)

    expect(offenders).toEqual([])
  })
})
