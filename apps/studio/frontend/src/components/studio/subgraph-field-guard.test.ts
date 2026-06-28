/// <reference types="node" />

import { readdirSync, readFileSync, statSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const FRONTEND_SRC_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..")
const D84_SURFACE_FILES = [
  "api/client.ts",
  "api/types.ts",
  "components/GraphCanvas/build-nodes.ts",
  "components/GraphCanvas/GraphCanvas.tsx",
  "components/GraphCanvas/canvas-authoring.ts",
  "components/GraphCanvas/subgraph-expansion.ts",
  "components/nodes/SkillNode.tsx",
  "components/nodes/SubgraphGroupNode.tsx",
  "components/studio/panels/AssetsPanel.tsx",
  "components/studio/panels/PropertiesPanel.tsx",
  "components/studio/panels/subgraph-membership.ts",
] as const
const PROPERTIES_PANEL_PATH = path.join(FRONTEND_SRC_ROOT, "components/studio/panels/PropertiesPanel.tsx")

function walkSourceFiles(root: string): string[] {
  const entries = readdirSync(root)
  return entries.flatMap((entry: string) => {
    const fullPath = path.join(root, entry)
    const stats = statSync(fullPath)
    if (stats.isDirectory()) {
      return walkSourceFiles(fullPath)
    }
    return fullPath.endsWith(".ts") || fullPath.endsWith(".tsx") ? [fullPath] : []
  })
}

describe("D8.4 frontend field guard", () => {
  it("keeps SUBGRAPH surfaces path-based and free of target_skill/targetSkill fields", () => {
    const expectedFiles = D84_SURFACE_FILES.map((relativePath) => path.join(FRONTEND_SRC_ROOT, relativePath))
    const discovered = new Set(walkSourceFiles(FRONTEND_SRC_ROOT))

    expect([...discovered]).toEqual(expect.arrayContaining(expectedFiles))

    for (const filePath of expectedFiles) {
      const source = readFileSync(filePath, "utf-8")
      const sanitized =
        filePath === PROPERTIES_PANEL_PATH
          ? source.replace(/function SubagentsField[\s\S]*$/, "")
          : source

      expect(sanitized).not.toMatch(/\btargetSkill\b/)
      expect(sanitized).not.toMatch(/\btarget_skill\b/)
    }
  })
})
