import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import { isValidElement, type ReactElement, type ReactNode } from "react"
import { ProviderCard, ProviderDeleteConfirmation, apiKeyInputClassName } from "./ProviderCard"
import type { CredentialsState } from "../../../api/llm"
import type { ProviderDraft } from "../SettingsPage"

const draft: ProviderDraft = {
  id: "p1",
  name: "OpenAI",
  api_key: "sk-secret-123",
  base_url: "",
  provider_type: "openai_compatible",
  isTesting: false,
}

function makeDraft(overrides: Partial<ProviderDraft> = {}): ProviderDraft {
  return { ...draft, ...overrides }
}

function makePersisted(
  overrides: Partial<CredentialsState["providers"][number]> = {},
): CredentialsState["providers"][number] {
  return {
    id: "p1",
    name: "OpenAI",
    api_key: "sk-secret-123",
    base_url: "",
    provider_type: "openai_compatible",
    ...overrides,
  }
}

function renderCardHtml({
  nextDraft = draft,
  persisted = null,
}: {
  nextDraft?: ProviderDraft
  persisted?: CredentialsState["providers"][number] | null
} = {}): string {
  return renderToStaticMarkup(
    <ProviderCard
      draft={nextDraft}
      persisted={persisted}
      onFieldChange={vi.fn()}
      onTest={vi.fn()}
      onDelete={vi.fn()}
    />,
  )
}

function textOf(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") {
    return ""
  }
  if (typeof node === "string" || typeof node === "number") {
    return String(node)
  }
  if (Array.isArray(node)) {
    return node.map(textOf).join("")
  }
  if (isValidElement(node)) {
    return textOf((node as ReactElement<{ children?: ReactNode }>).props.children)
  }
  return ""
}

function findElement(
  node: ReactNode,
  predicate: (element: ReactElement<Record<string, unknown>>) => boolean,
): ReactElement<Record<string, unknown>> | null {
  if (!isValidElement(node)) {
    return null
  }

  const element = node as ReactElement<Record<string, unknown>>
  if (predicate(element)) {
    return element
  }

  const children = element.props.children as ReactNode
  if (Array.isArray(children)) {
    for (const child of children) {
      const match = findElement(child, predicate)
      if (match) return match
    }
    return null
  }
  return findElement(children, predicate)
}

describe("ProviderCard API key masking", () => {
  it("renders API key as masked text input by default", () => {
    const html = renderCardHtml()

    expect(html).toContain('type="text"')
    expect(html).toContain('value="sk-secret-123"')
    expect(html).toContain("mask-input")
    expect(html).toContain('name="provider-secret-p1"')
    expect(html).toContain('data-1p-ignore=""')
    expect(html).toContain('data-lpignore="true"')
    expect(html).toContain('data-form-type="other"')
    expect(html).toContain('aria-label="Show API key"')
    expect(html).toContain("transition-none")
    expect(html).toContain("px-6")
  })

  it("visibility toggle changes only mask class and does not mutate draft api key", () => {
    const onFieldChange = vi.fn()
    const hiddenClassName = apiKeyInputClassName(false)
    const visibleClassName = apiKeyInputClassName(true)

    expect(hiddenClassName).toContain("mask-input")
    expect(visibleClassName).not.toContain("mask-input")
    expect(onFieldChange).not.toHaveBeenCalled()
    expect(draft.api_key).toBe("sk-secret-123")
  })
})

describe("ProviderCard test status badge", () => {
  it("renders Untested as secondary badge", () => {
    const html = renderCardHtml()

    expect(html).toContain('data-variant="secondary"')
    expect(html).toContain("Untested")
  })

  it("renders Testing badge with spinner", () => {
    const html = renderCardHtml({ nextDraft: makeDraft({ isTesting: true }) })

    expect(html).toContain("Testing...")
    expect(html).toContain("animate-spin")
  })

  it("renders Connected badge with emerald utility color", () => {
    const html = renderCardHtml({ persisted: makePersisted({ last_test_status: "ok" }) })

    expect(html).toContain("Connected")
    expect(html).toContain("text-emerald-500")
    expect(html).toContain("border-emerald-500/50")
  })

  it("renders Error badge as destructive with error code", () => {
    const html = renderCardHtml({
      persisted: makePersisted({ last_test_status: "error", last_error_code: "auth_failed" }),
    })

    expect(html).toContain('data-variant="destructive"')
    expect(html).toContain("auth_failed")
  })
})

describe("ProviderCard provider kind badge", () => {
  it("renders Official badge when providerKind is official", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={draft}
        persisted={null}
        onFieldChange={vi.fn()}
        onTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    expect(html).toContain("Official")
  })

  it("renders Third-party badge when providerKind is third-party", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={draft}
        persisted={null}
        onFieldChange={vi.fn()}
        onTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="third-party"
      />,
    )

    expect(html).toContain("Third-party")
  })
})

describe("ProviderCard delete confirmation", () => {
  it("delete trigger opens confirmation without calling onDelete directly", () => {
    const onDelete = vi.fn()
    const element = ProviderDeleteConfirmation({ draftName: "OpenAI", onDelete })
    const trigger = findElement(element, (candidate) => candidate.props["aria-label"] === "Delete provider")

    expect(textOf(element)).toContain("确认删除 OpenAI?")
    expect(textOf(element)).toContain("此操作不可恢复, 该 provider 配置将永久删除。")
    expect(textOf(element)).toContain("取消")
    expect(trigger?.props.onClick).toBeUndefined()
    expect(onDelete).not.toHaveBeenCalled()
  })

  it("confirm action is wired to call onDelete", () => {
    const onDelete = vi.fn()
    const element = ProviderDeleteConfirmation({ draftName: "OpenAI", onDelete })
    const confirm = findElement(
      element,
      (candidate) => textOf(candidate).trim() === "删除" && candidate.props.onClick === onDelete,
    )

    expect(confirm).not.toBeNull()
    ;(confirm!.props.onClick as () => void)()
    expect(onDelete).toHaveBeenCalledTimes(1)
  })
})
