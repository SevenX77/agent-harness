import { describe, expect, it } from "vitest"
import enSettings from "@/locales/en/settings.json"
import zhSettings from "@/locales/zh-CN/settings.json"

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
