import { describe, expect, it, vi } from "vitest"
import { applyLanguageChange } from "./language-switch"

/**
 * N0 i18n (#15.1) — the General-tab language switch must do two things on change,
 * and both are tested here as a DOM-free pure helper (repo convention: no
 * @testing-library/react / jsdom):
 *   1. drive the live UI language via i18n.changeLanguage(value)
 *   2. persist the choice into AppSettings via setLanguage(value)
 * so the selection survives reload and propagates across windows through the
 * existing settings store.
 */

describe("applyLanguageChange", () => {
  it("drives the live UI language through i18n.changeLanguage", () => {
    const changeLanguage = vi.fn().mockResolvedValue(undefined)
    const setLanguage = vi.fn()

    applyLanguageChange({ changeLanguage, setLanguage, value: "zh-CN" })

    expect(changeLanguage).toHaveBeenCalledWith("zh-CN")
  })

  it("persists the selected language into AppSettings", () => {
    const changeLanguage = vi.fn().mockResolvedValue(undefined)
    const setLanguage = vi.fn()

    applyLanguageChange({ changeLanguage, setLanguage, value: "zh-CN" })

    expect(setLanguage).toHaveBeenCalledWith("zh-CN")
  })

  it("ignores unsupported language values (no live switch, no persist)", () => {
    const changeLanguage = vi.fn().mockResolvedValue(undefined)
    const setLanguage = vi.fn()

    applyLanguageChange({ changeLanguage, setLanguage, value: "fr-FR" })

    expect(changeLanguage).not.toHaveBeenCalled()
    expect(setLanguage).not.toHaveBeenCalled()
  })

  it("still persists even if the live i18n switch rejects", async () => {
    const changeLanguage = vi.fn().mockRejectedValue(new Error("i18n boom"))
    const setLanguage = vi.fn()

    applyLanguageChange({ changeLanguage, setLanguage, value: "en" })

    // persistence is independent of the async i18n switch resolving
    expect(setLanguage).toHaveBeenCalledWith("en")
    // the rejected changeLanguage promise must be swallowed (no unhandled rejection)
    await Promise.resolve()
  })
})
