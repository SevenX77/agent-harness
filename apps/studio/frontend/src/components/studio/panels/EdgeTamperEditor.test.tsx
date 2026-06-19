import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { ComponentProps } from "react"

// EdgeTamperEditor reuses the project Monaco surface (the same `@monaco-editor/react`
// the skill editor uses). Monaco is heavy and DOM-driven, so stub it to a marker that
// echoes the props we care about (value / readOnly / language) for a pure SSR test.
const monacoCalls: Array<Record<string, unknown>> = []
vi.mock("@monaco-editor/react", () => ({
  default: (props: ComponentProps<"div"> & Record<string, unknown>) => {
    monacoCalls.push(props)
    return null
  },
}))

const { EdgeTamperEditor } = await import("./EdgeTamperEditor")
const { default: MonacoEditor } = (await import("@monaco-editor/react")) as unknown as {
  default: (props: Record<string, unknown>) => null
}

function render(props: Partial<ComponentProps<typeof EdgeTamperEditor>> = {}): string {
  return renderToStaticMarkup(
    <EdgeTamperEditor
      value={'{\n  "topic": "cats"\n}'}
      writable={false}
      onChange={() => undefined}
      onStartTamper={() => undefined}
      onCancel={() => undefined}
      onResume={() => undefined}
      checkpointId="checkpoint-review"
      {...props}
    />,
  )
}

describe("EdgeTamperEditor", () => {
  it("mounts the project Monaco editor (not a plain textarea) for context tampering", () => {
    monacoCalls.length = 0
    renderToStaticMarkup(
      <EdgeTamperEditor
        value="{}"
        writable
        onChange={() => undefined}
        onStartTamper={() => undefined}
        onCancel={() => undefined}
        onResume={() => undefined}
      />,
    )
    expect(MonacoEditor).toBeTypeOf("function")
    expect(monacoCalls.length).toBeGreaterThan(0)
    const props = monacoCalls.at(-1) ?? {}
    // JSON language so the editor gives JSON syntax affordances.
    expect(props.defaultLanguage ?? props.language).toBe("json")
    expect(props.value).toBe("{}")
  })

  it("is read-only until tamper is started (Q3: read-only trace surface switched writable)", () => {
    monacoCalls.length = 0
    render({ writable: false })
    const props = monacoCalls.at(-1) ?? {}
    const options = (props.options ?? {}) as Record<string, unknown>
    expect(options.readOnly).toBe(true)
  })

  it("switches the same editor writable once tampering (no separate component)", () => {
    monacoCalls.length = 0
    render({ writable: true })
    const props = monacoCalls.at(-1) ?? {}
    const options = (props.options ?? {}) as Record<string, unknown>
    expect(options.readOnly).toBe(false)
  })

  it("exposes Tamper entry, the checkpoint anchor, and a labelled editor region", () => {
    const html = render({ writable: false })
    expect(html).toContain("Tamper")
    expect(html).toContain("checkpoint-review")
    expect(html).toContain('aria-label="Tampered edge context JSON"')
  })

  it("surfaces a live JSON validity error when the writable draft is malformed", () => {
    const html = render({ writable: true, value: '{"topic":' })
    // The shared validateTamperJson rule drives a visible, observable error.
    expect(html).toContain("Invalid JSON")
  })

  it("reads valid (no error) when the writable draft is a well-formed object", () => {
    const html = render({ writable: true, value: '{"topic":"dogs"}' })
    expect(html).not.toContain("Invalid JSON")
  })

  it("uses semantic tokens for the validity error — never hardcoded palette colors", () => {
    const html = render({ writable: true, value: '{"topic":' })
    expect(html).toContain("destructive")
    expect(html).not.toMatch(/red-\d/)
    expect(html).not.toMatch(/slate-\d/)
  })
})
