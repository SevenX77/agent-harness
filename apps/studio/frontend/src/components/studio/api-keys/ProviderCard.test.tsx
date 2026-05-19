import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import { isValidElement, type ReactElement, type ReactNode } from "react"
import { ProviderCard, ProviderDeleteConfirmation, apiKeyInputClassName } from "./ProviderCard"
import type { ProviderDraft } from "../SettingsPage"

const draft: ProviderDraft = {
  id: "p1",
  name: "OpenAI",
  api_key: "sk-secret-123",
  base_url: "",
  provider_type: "openai_compatible",
  isTesting: false,
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
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={draft}
        persisted={null}
        onFieldChange={vi.fn()}
        onTest={vi.fn()}
        onDelete={vi.fn()}
      />,
    )

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
