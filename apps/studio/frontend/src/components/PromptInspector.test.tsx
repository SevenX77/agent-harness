import { renderToStaticMarkup } from "react-dom/server"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import { PromptInspector } from "./PromptInspector"
import type { CallbackEvent } from "../api/types"

vi.mock("./ui/dialog", () => ({
  Dialog: ({ children }: { children: ReactNode }) => <div data-slot="dialog">{children}</div>,
  DialogContent: ({ children }: { children: ReactNode }) => <div data-slot="dialog-content">{children}</div>,
  DialogHeader: ({ children }: { children: ReactNode }) => <div data-slot="dialog-header">{children}</div>,
  DialogTitle: ({ children }: { children: ReactNode }) => <h2 data-slot="dialog-title">{children}</h2>,
}))

vi.mock("./ui/tabs", () => ({
  Tabs: ({ children }: { children: ReactNode }) => <div data-slot="tabs">{children}</div>,
  TabsContent: ({ children }: { children: ReactNode }) => <div data-slot="tabs-content">{children}</div>,
  TabsList: ({ children }: { children: ReactNode }) => <div data-slot="tabs-list">{children}</div>,
  TabsTrigger: ({ children }: { children: ReactNode }) => <button data-slot="tabs-trigger">{children}</button>,
}))

const promptEvent = {
  event_type: "prompt_captured",
  phase_id: "draft",
  template_source: "template body",
  variables: { topic: "demo" },
  resolved_prompt: { messages: [] },
} as unknown as CallbackEvent

describe("PromptInspector", () => {
  it("uses shadcn dialog and tabs primitives instead of a custom overlay", () => {
    const html = renderToStaticMarkup(<PromptInspector promptEvent={promptEvent} onClose={vi.fn()} />)

    expect(html).toContain('data-slot="dialog-content"')
    expect(html).toContain('data-slot="tabs"')
    expect(html).toContain('data-slot="tabs-trigger"')
    expect(html).not.toContain("bg-slate")
    expect(html).not.toContain("bg-gray")
    expect(html).not.toContain("text-violet")
  })

  // trace-observability F7: the inspector names the model that served the call.
  it("shows the resolved model in the header when the event carries one", () => {
    const withModel = { ...promptEvent, resolved_model: "claude-sonnet-4-6" } as unknown as CallbackEvent
    const html = renderToStaticMarkup(<PromptInspector promptEvent={withModel} onClose={vi.fn()} />)
    expect(html).toContain("claude-sonnet-4-6")
  })

  it("renders no model chip when the event carries no model", () => {
    const html = renderToStaticMarkup(<PromptInspector promptEvent={promptEvent} onClose={vi.fn()} />)
    expect(html).not.toContain("prompt-inspector-model")
  })
})
