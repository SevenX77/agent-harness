import { describe, expect, it } from "vitest"
import yaml from "js-yaml"
import { applyInputSchemaToGraph, inferJsonSchemaFromText } from "./schema-infer"

const GRAPH = `---
schema_version: "v0.3.0"
name: demo
io:
  inputs:
    type: object
    required: [old]
    properties:
      old:
        type: string
  outputs:
    type: object
    required: [final_result]
    properties:
      final_result:
        type: string
phases:
  - step1
---
<phase depends_on="input">step1</phase>
`

describe("applyInputSchemaToGraph (F2 schema writeback)", () => {
  it("replaces io.inputs with the inferred schema, preserving outputs + body", () => {
    const inferred = inferJsonSchemaFromText('{"payload": "hi"}')
    const next = applyInputSchemaToGraph(GRAPH, inferred)

    // Body (phase DAG) is preserved verbatim.
    expect(next).toContain('<phase depends_on="input">step1</phase>')

    const fm = next.match(/^---\n([\s\S]*?)\n---/)
    expect(fm).not.toBeNull()
    const data = yaml.load(fm![1]) as Record<string, unknown>
    const io = data.io as Record<string, unknown>

    // io.inputs is now the inferred schema (old field gone, payload present).
    const inputs = io.inputs as { properties?: Record<string, unknown>; required?: string[] }
    expect(inputs.properties).toHaveProperty("payload")
    expect(inputs.properties).not.toHaveProperty("old")
    expect(inputs.required).toEqual(["payload"])

    // io.outputs and other frontmatter keys are untouched.
    const outputs = io.outputs as { required?: string[] }
    expect(outputs.required).toEqual(["final_result"])
    expect(data.schema_version).toBe("v0.3.0")
    expect(data.name).toBe("demo")
  })

  it("throws a clear error when GRAPH.md has no frontmatter", () => {
    expect(() => applyInputSchemaToGraph("no frontmatter here", { type: "object" })).toThrow(
      /frontmatter/,
    )
  })
})
