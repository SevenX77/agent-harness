import { afterAll, describe, expect, it } from "vitest"
import i18n from "@/i18n"
import enSettings from "@/locales/en/settings.json"
import zhSettings from "@/locales/zh-CN/settings.json"
import { routeTooltipLineStatus } from "./ProviderCard"

// i18n contract for the API Keys card surface extracted in the AddProviderForm +
// ManualModelTestPanel pass: every key these components emit through t()/i18n.t()
// must exist in BOTH the en and zh-CN bundles, keep its named placeholders (so no
// language silently drops an interpolation), and the zh-CN copy must be real
// Chinese rather than the English string leaking through. See FRONTEND_UI_SPEC §2.5.
const CJK = /[一-鿿]/

const en = enSettings.apiKeys
const zh = zhSettings.apiKeys

describe("apiKeys.form i18n bundle contract", () => {
  const keys = [
    "providerNameLabel",
    "providerNamePlaceholder",
    "providerNameRequired",
    "providerNameDuplicate",
    "baseUrlLabel",
    "baseUrlPlaceholder",
    "apiKeyLabel",
    "apiKeyPlaceholder",
    "cancelButton",
  ] as const

  it("en + zh define every apiKeys.form key", () => {
    for (const key of keys) {
      expect(en.form[key], `en apiKeys.form.${key}`).toBeTruthy()
      expect(zh.form[key], `zh apiKeys.form.${key}`).toBeTruthy()
    }
  })

  it("zh translates the human-language form copy (not raw English)", () => {
    // Labels that are intentionally protocol/URL tokens (Base URL, API Key, the
    // url placeholder) stay ASCII on purpose; the prose strings must be Chinese.
    expect(zh.form.providerNameLabel).toMatch(CJK)
    expect(zh.form.providerNameRequired).toMatch(CJK)
    expect(zh.form.providerNameDuplicate).toMatch(CJK)
    expect(zh.form.apiKeyPlaceholder).toMatch(CJK)
    expect(zh.form.cancelButton).toMatch(CJK)
    expect(zh.form.providerNameRequired).not.toBe(en.form.providerNameRequired)
  })
})

describe("apiKeys.manualTest i18n bundle contract", () => {
  const flatKeys = [
    "title",
    "description",
    "placeholderExample",
    "modelInputLabel",
    "removeModelLabel",
    "addModel",
    "testModels",
    "testingLoading",
    "candidateLoadError",
    "testFailedFallback",
    "noResults",
    "oneAvailable",
    "manyAvailable",
    "someFailed",
    "failedItem",
  ] as const
  const statusKeys = [
    "ok",
    "invalidModel",
    "invalidKey",
    "rateLimited",
    "quotaExceeded",
    "networkError",
    "timeout",
    "failed",
  ] as const

  it("en + zh define every apiKeys.manualTest key (flat + status)", () => {
    for (const key of flatKeys) {
      expect(en.manualTest[key], `en apiKeys.manualTest.${key}`).toBeTruthy()
      expect(zh.manualTest[key], `zh apiKeys.manualTest.${key}`).toBeTruthy()
    }
    for (const key of statusKeys) {
      expect(en.manualTest.status[key], `en status.${key}`).toBeTruthy()
      expect(zh.manualTest.status[key], `zh status.${key}`).toBeTruthy()
    }
  })

  it("both languages preserve named placeholders (no interpolation dropped)", () => {
    for (const bundle of [en.manualTest, zh.manualTest]) {
      expect(bundle.placeholderExample).toContain("{{example}}")
      expect(bundle.modelInputLabel).toContain("{{index}}")
      expect(bundle.removeModelLabel).toContain("{{index}}")
      expect(bundle.manyAvailable).toContain("{{n}}")
      expect(bundle.someFailed).toContain("{{failed}}")
      expect(bundle.someFailed).toContain("{{total}}")
      expect(bundle.failedItem).toContain("{{modelId}}")
      expect(bundle.failedItem).toContain("{{status}}")
    }
  })

  it("zh translates the manual-test prose + status labels to Chinese", () => {
    expect(zh.manualTest.title).toMatch(CJK)
    expect(zh.manualTest.description).toMatch(CJK)
    expect(zh.manualTest.addModel).toMatch(CJK)
    expect(zh.manualTest.testModels).toMatch(CJK)
    expect(zh.manualTest.status.ok).toMatch(CJK)
    expect(zh.manualTest.status.timeout).toMatch(CJK)
    expect(zh.manualTest.status.ok).not.toBe(en.manualTest.status.ok)
  })
})

describe("apiKeys.card i18n bundle contract", () => {
  type JsonValue = string | { [key: string]: JsonValue }

  // Walk the en.card tree and assert every leaf key also exists (and is
  // non-empty) in zh.card; collect every leaf path for the placeholder /
  // translation checks below.
  function leafPaths(node: JsonValue, prefix = ""): string[] {
    if (typeof node === "string") return [prefix]
    return Object.entries(node).flatMap(([key, value]) =>
      leafPaths(value, prefix ? `${prefix}.${key}` : key),
    )
  }

  function lookup(node: JsonValue, path: string): string {
    const value = path
      .split(".")
      .reduce<JsonValue | undefined>((acc, key) => (acc && typeof acc === "object" ? acc[key] : undefined), node)
    return typeof value === "string" ? value : ""
  }

  const enCard = en.card as JsonValue
  const zhCard = zh.card as JsonValue
  const cardPaths = leafPaths(enCard)

  // {{count}} would silently flip i18next into plural mode (looks up *_other) —
  // proving none of the card keys use it guards against the documented gotcha.
  const placeholderPattern = /\{\{(\w+)\}\}/g

  // Values that are legitimately identical across languages: technical/brand
  // tokens, URLs, and a CJK-free protocol short labels block.
  const sharedTokenPaths = new Set([
    "protocolShort.anthropic",
    "protocolShort.gemini",
    "protocolShort.openai",
    "protocolShort.ark",
    "protocolShort.unknown",
    "protocol.google",
    "baseUrlPlaceholder1",
    "baseUrlPlaceholder2",
    "apiKeyLabel",
    "apiKeyShort",
    "baseUrlLabel",
    "baseUrlFallback",
    "modality.pdf",
    "modality.threeD",
    "routeGroup.threeD",
    "tooltip.sdks",
  ])

  it("en + zh define every apiKeys.card.* leaf key", () => {
    expect(cardPaths.length).toBeGreaterThan(40)
    for (const path of cardPaths) {
      expect(lookup(enCard, path), `en apiKeys.card.${path}`).toBeTruthy()
      expect(lookup(zhCard, path), `zh apiKeys.card.${path}`).toBeTruthy()
    }
  })

  it("never uses the {{count}} plural trigger (uses {{n}} instead)", () => {
    for (const path of cardPaths) {
      expect(lookup(enCard, path), `en ${path} must not use {{count}}`).not.toContain("{{count}}")
      expect(lookup(zhCard, path), `zh ${path} must not use {{count}}`).not.toContain("{{count}}")
    }
  })

  it("both languages preserve the same named placeholders per key", () => {
    for (const path of cardPaths) {
      const enPlaceholders = (lookup(enCard, path).match(placeholderPattern) ?? []).sort()
      const zhPlaceholders = (lookup(zhCard, path).match(placeholderPattern) ?? []).sort()
      expect(zhPlaceholders, `placeholders differ for apiKeys.card.${path}`).toEqual(enPlaceholders)
    }
  })

  it("spot-checks the documented placeholders are present", () => {
    expect(en.card.connectedWithLatency).toContain("{{latencyMs}}")
    expect(en.card.copiedToast).toContain("{{label}}")
    expect(en.card.apiKeyPlaceholder).toContain("{{providerName}}")
    expect(en.card.showMoreButton).toContain("{{n}}")
    expect(en.card.moreActionsButton).toContain("{{draftName}}")
    expect(en.card.baseUrlConnected).toContain("{{url}}")
    expect(en.card.tooltip.endpoint).toContain("{{id}}")
    expect(en.card.tooltip.protocol).toContain("{{protocol}}")
    expect(en.card.tooltip.status).toContain("{{status}}")
    expect(en.card.tooltip.methods).toContain("{{methods}}")
    expect(en.card.tooltip.requestMappers).toContain("{{mappers}}")
    expect(en.card.tooltip.profileCapabilities).toContain("{{capabilities}}")
    expect(en.card.tooltip.lastTest).toContain("{{timestamp}}")
    expect(en.card.tooltip.message).toContain("{{message}}")
    expect(en.card.tooltip.errorCode).toContain("{{code}}")
    expect(en.card.deleteConfirm.title).toContain("{{displayName}}")
  })

  it("zh card copy is real Chinese (except whitelisted technical/brand tokens)", () => {
    for (const path of cardPaths) {
      if (sharedTokenPaths.has(path)) continue
      const zhValue = lookup(zhCard, path)
      const enValue = lookup(enCard, path)
      // Strip interpolation tokens before the CJK check so a value made only of
      // a placeholder + ASCII punctuation isn't penalised.
      const zhProse = zhValue.replace(placeholderPattern, "").trim()
      expect(zhProse, `zh apiKeys.card.${path} should contain Chinese`).toMatch(CJK)
      expect(zhValue, `zh apiKeys.card.${path} should differ from en`).not.toBe(enValue)
    }
  })

  it("modality + capability labels are real Chinese", () => {
    expect(zh.card.modality.text).toBe("文本")
    expect(zh.card.modality.image).toBe("图像")
    expect(zh.card.modality.audio).toBe("音频")
    expect(zh.card.capability.toolCalling).toMatch(CJK)
    expect(zh.card.capability.reasoning).toMatch(CJK)
    expect(zh.card.routeStatus.previouslyConnected).toMatch(CJK)
    expect(zh.card.protocol.anthropic).toMatch(CJK)
  })
})

// The tooltip warning/failure icon is painted by routeTooltipLineStatus(). After
// i18n the displayed text is translated, so classification must NOT match the
// (now-translated) display literals — it keys off a language-independent
// sentinel the line-builders prepend. This guards the documented coupling: a
// failed/endpoint-failed route must still light up its icon under zh-CN.
describe("routeTooltipLineStatus stays language-independent", () => {
  // Mirror the sentinels embedded by markTooltipDiagnostic() in ProviderCard.
  const SENTINEL_WARNING = "​⚠​"
  const SENTINEL_FAILED = "​✗​"

  afterAll(async () => {
    await i18n.changeLanguage("en")
  })

  it("classifies sentinel-marked lines regardless of the active language", async () => {
    for (const lng of ["en", "zh-CN"] as const) {
      await i18n.changeLanguage(lng)
      const failLine = SENTINEL_FAILED + i18n.t("apiKeys.card.routeTooltip.routeTestFailedBare")
      const warnLine = SENTINEL_WARNING + i18n.t("apiKeys.card.routeStatus.endpointFailed")
      const plainLine = i18n.t("apiKeys.card.tooltip.status", { status: "x" })
      expect(routeTooltipLineStatus(failLine), `failed @ ${lng}`).toBe("failed")
      expect(routeTooltipLineStatus(warnLine), `warning @ ${lng}`).toBe("warning")
      expect(routeTooltipLineStatus(plainLine), `null @ ${lng}`).toBeNull()
    }
  })

  it("still classifies the legacy English literals (pure-function fallback)", () => {
    expect(routeTooltipLineStatus("gpt-broken - Route test failed: 401.")).toBe("failed")
    expect(routeTooltipLineStatus("gpt-5 - Warning: Thinking was preferred.")).toBe("warning")
    expect(routeTooltipLineStatus("Endpoint failed: ep1")).toBe("warning")
    expect(routeTooltipLineStatus("Model failed: gpt-x")).toBe("failed")
    expect(routeTooltipLineStatus("Input: text")).toBeNull()
  })
})
