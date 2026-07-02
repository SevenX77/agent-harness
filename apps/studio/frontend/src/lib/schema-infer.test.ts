import { describe, expect, it } from "vitest"
import yaml from "js-yaml"
import {
  addIoField,
  applyInputSchemaToGraph,
  inferJsonSchemaFromText,
  listIoFields,
  removeIoField,
  renameIoField,
  setIoFieldType,
} from "./schema-infer"

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

function ioOf(graphMd: string): { inputs: Record<string, unknown>; outputs: Record<string, unknown> } {
  const fm = graphMd.match(/^---\n([\s\S]*?)\n---/)
  const data = yaml.load(fm![1]) as Record<string, unknown>
  const io = data.io as Record<string, unknown>
  return { inputs: io.inputs as Record<string, unknown>, outputs: io.outputs as Record<string, unknown> }
}

describe("listIoFields", () => {
  it("lists declared input and output fields with their json-schema types", () => {
    expect(listIoFields(GRAPH, "inputs")).toEqual([{ name: "old", type: "string" }])
    expect(listIoFields(GRAPH, "outputs")).toEqual([{ name: "final_result", type: "string" }])
  })

  it("returns [] when GRAPH.md has no frontmatter", () => {
    expect(listIoFields("no frontmatter", "inputs")).toEqual([])
  })
})

describe("addIoField (field-level io editor)", () => {
  it("adds a typed field to io.inputs, preserving outputs + body + other keys", () => {
    const next = addIoField(GRAPH, "inputs", "topic", "string")

    // Body (phase DAG) survives.
    expect(next).toContain('<phase depends_on="input">step1</phase>')

    const { inputs, outputs } = ioOf(next)
    const inputProps = (inputs.properties as Record<string, { type?: string }>)
    expect(inputProps.old.type).toBe("string")
    expect(inputProps.topic.type).toBe("string")
    // The other io side and its required[] are untouched.
    expect((outputs.properties as Record<string, unknown>)).toHaveProperty("final_result")
    expect(outputs.required).toEqual(["final_result"])
  })

  it("adds to io.outputs independently of io.inputs", () => {
    const next = addIoField(GRAPH, "outputs", "score", "number")
    const { inputs, outputs } = ioOf(next)
    expect((outputs.properties as Record<string, { type?: string }>).score.type).toBe("number")
    // io.inputs unchanged.
    expect(Object.keys(inputs.properties as Record<string, unknown>)).toEqual(["old"])
  })

  it("throws when the field name is blank", () => {
    expect(() => addIoField(GRAPH, "inputs", "   ", "string")).toThrow(/empty/)
  })

  it("throws when the field already exists", () => {
    expect(() => addIoField(GRAPH, "inputs", "old", "string")).toThrow(/already declares/)
  })
})

describe("removeIoField (field-level io editor)", () => {
  it("removes a field from io.inputs and drops it from required, preserving the rest", () => {
    const withExtra = addIoField(GRAPH, "inputs", "topic", "string")
    const next = removeIoField(withExtra, "inputs", "old")

    expect(next).toContain('<phase depends_on="input">step1</phase>')
    const { inputs, outputs } = ioOf(next)
    const inputProps = inputs.properties as Record<string, unknown>
    expect(inputProps).not.toHaveProperty("old")
    expect(inputProps).toHaveProperty("topic")
    // `old` was in required[] — it must be dropped there too.
    expect(inputs.required).toEqual([])
    // io.outputs untouched.
    expect((outputs.properties as Record<string, unknown>)).toHaveProperty("final_result")
  })

  it("throws when the field does not exist", () => {
    expect(() => removeIoField(GRAPH, "inputs", "nope")).toThrow(/no field named "nope"/)
  })
})

describe("renameIoField (field-level io editor)", () => {
  it("renames a field, preserving its schema + updating required, keeping body", () => {
    const next = renameIoField(GRAPH, "inputs", "old", "fresh")

    expect(next).toContain('<phase depends_on="input">step1</phase>')
    const { inputs } = ioOf(next)
    const inputProps = inputs.properties as Record<string, { type?: string }>
    expect(inputProps).not.toHaveProperty("old")
    expect(inputProps.fresh.type).toBe("string")
    // required[] follows the rename.
    expect(inputs.required).toEqual(["fresh"])
  })

  it("renames an output field independently of inputs", () => {
    const next = renameIoField(GRAPH, "outputs", "final_result", "answer")
    const { inputs, outputs } = ioOf(next)
    expect((outputs.properties as Record<string, unknown>)).toHaveProperty("answer")
    expect(outputs.required).toEqual(["answer"])
    // inputs untouched.
    expect((inputs.properties as Record<string, unknown>)).toHaveProperty("old")
  })

  it("is a no-op when renaming to the same name", () => {
    const next = renameIoField(GRAPH, "inputs", "old", "old")
    expect(listIoFields(next, "inputs")).toEqual([{ name: "old", type: "string" }])
  })

  it("throws when the source field is missing", () => {
    expect(() => renameIoField(GRAPH, "inputs", "ghost", "x")).toThrow(/no field named "ghost"/)
  })

  it("throws when the target name collides", () => {
    const two = addIoField(GRAPH, "inputs", "topic", "string")
    expect(() => renameIoField(two, "inputs", "old", "topic")).toThrow(/already declares/)
  })

  it("throws when the new name is blank", () => {
    expect(() => renameIoField(GRAPH, "inputs", "old", "  ")).toThrow(/empty/)
  })
})

describe("setIoFieldType (field-level io editor)", () => {
  it("changes a field's type, preserving the rest of the frontmatter + body", () => {
    const next = setIoFieldType(GRAPH, "inputs", "old", "integer")

    expect(next).toContain('<phase depends_on="input">step1</phase>')
    const { inputs, outputs } = ioOf(next)
    expect((inputs.properties as Record<string, { type?: string }>).old.type).toBe("integer")
    // required[] and the other io side are preserved.
    expect(inputs.required).toEqual(["old"])
    expect(outputs.required).toEqual(["final_result"])
  })

  it("throws when the field does not exist", () => {
    expect(() => setIoFieldType(GRAPH, "outputs", "missing", "number")).toThrow(/no field named "missing"/)
  })
})
