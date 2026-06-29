import { describe, expect, it } from "vitest"
import {
  actionFilePath,
  actionStubContent,
  applyActionsList,
  isValidActionName,
  parseBodyActions,
  readActionsList,
  scanActionFiles,
} from "./phase-actions"

describe("phase-actions helpers", () => {
  it("builds the actions/<name>.py path for a phase", () => {
    expect(actionFilePath("normalize", "strip_noise")).toBe("phases/normalize/actions/strip_noise.py")
  })

  it("accepts Python-identifier action names and rejects the rest", () => {
    expect(isValidActionName("strip_noise")).toBe(true)
    expect(isValidActionName("_private")).toBe(true)
    expect(isValidActionName("Step2")).toBe(true)
    expect(isValidActionName("")).toBe(false)
    expect(isValidActionName("2step")).toBe(false)
    expect(isValidActionName("a.b")).toBe(false)
    expect(isValidActionName("a/b")).toBe(false)
    expect(isValidActionName("has space")).toBe(false)
  })

  it("generates a load-safe stub following the action convention", () => {
    const stub = actionStubContent("strip_noise")
    expect(stub).toContain("from __future__ import annotations")
    expect(stub).toContain("def strip_noise(context) -> dict:")
    expect(stub).toContain("return {}")
  })

  it("reads the canonical action list from frontmatter", () => {
    const md = ["---", "name: normalize", "actions:", "  - a", "  - b", "---", "<action>a</action>"].join("\n")
    expect(readActionsList(md)).toEqual(["a", "b"])
    expect(readActionsList(["---", "name: x", "actions: []", "---", ""].join("\n"))).toEqual([])
  })

  it("parses body <action> tags in order, ignoring empty ones", () => {
    const body = "<action>first</action>\n<action></action>\n<action>second</action>"
    expect(parseBodyActions(body)).toEqual(["first", "second"])
  })

  it("scans only this phase's actions/*.py files from the files map", () => {
    const files = {
      "phases/normalize/actions/strip_noise.py": "x",
      "phases/normalize/actions/squash.py": "x",
      "phases/normalize/actions/__init__.py": "x",
      "phases/other/actions/elsewhere.py": "x",
      "phases/normalize/LOGIC.md": "x",
    }
    expect([...scanActionFiles(files, "normalize")].sort()).toEqual(["squash", "strip_noise"])
  })

  it("adds an action to both frontmatter actions: and body <action> tags", () => {
    const md = ["---", "name: normalize", "actions:", "  - strip_noise", "---", "<action>strip_noise</action>", ""].join("\n")
    const result = applyActionsList(md, ["strip_noise", "squash"])
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.markdown).toContain("- strip_noise")
    expect(result.markdown).toContain("- squash")
    expect(result.markdown).toContain("<action>strip_noise</action>")
    expect(result.markdown).toContain("<action>squash</action>")
  })

  it("removes an action from both frontmatter and body", () => {
    const md = [
      "---",
      "name: normalize",
      "actions:",
      "  - strip_noise",
      "  - squash",
      "---",
      "<action>strip_noise</action>",
      "<action>squash</action>",
      "",
    ].join("\n")
    const result = applyActionsList(md, ["strip_noise"])
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.markdown).toContain("<action>strip_noise</action>")
    expect(result.markdown).not.toContain("squash")
  })

  it("keeps frontmatter and body action lists identical after a change", () => {
    const md = ["---", "name: normalize", "actions: []", "---", "<action></action>", ""].join("\n")
    const result = applyActionsList(md, ["a", "b", "c"])
    expect(result.ok).toBe(true)
    if (!result.ok) return
    const parsedBody = parseBodyActions(result.markdown)
    expect(parsedBody).toEqual(["a", "b", "c"])
    // frontmatter list must match body list exactly (engine requirement)
    for (const name of parsedBody) {
      expect(result.markdown).toContain(`- ${name}`)
    }
  })

  it("preserves unrelated frontmatter keys when editing actions", () => {
    const md = [
      "---",
      "name: normalize",
      "validator: true",
      "actions:",
      "  - strip_noise",
      "---",
      "<action>strip_noise</action>",
      "",
    ].join("\n")
    const result = applyActionsList(md, ["strip_noise", "squash"])
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.markdown).toContain("name: normalize")
    expect(result.markdown).toContain("validator: true")
  })
})
