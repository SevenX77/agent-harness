import { supportedLngs } from "@/i18n"
import type { AppLanguage } from "@/api/types"

/**
 * N0 i18n (#15.1): the single place the General-tab language switch funnels a
 * language change through. It does the two things the spec (i18n.md §7) requires
 * on change — drive the live UI language and persist the choice into
 * AppSettings — so the selection takes effect immediately AND survives reload /
 * propagates across windows via the settings store. Kept as a DOM-free pure
 * helper so both behaviours are unit-testable without a browser env.
 */
export interface ApplyLanguageChangeArgs {
  /** react-i18next's `i18n.changeLanguage`, injected so this stays test-pure. */
  changeLanguage: (language: string) => Promise<unknown>
  /** Persists the choice into AppSettings (`useAppSettings().setLanguage`). */
  setLanguage: (language: AppLanguage) => void
  /** Raw value emitted by the Select's `onValueChange`. */
  value: string
}

function isSupportedLanguage(value: string): value is AppLanguage {
  return (supportedLngs as readonly string[]).includes(value)
}

export function applyLanguageChange({ changeLanguage, setLanguage, value }: ApplyLanguageChangeArgs): void {
  if (!isSupportedLanguage(value)) {
    console.warn("phase=settings-language action=ignored-unsupported-language value=%s", value)
    return
  }
  // Persist first so the durable choice is recorded even if the live switch
  // (which spawns no I/O of our own) rejects for any reason.
  setLanguage(value)
  changeLanguage(value).catch((error) => {
    console.warn("phase=settings-language action=change-language-failed language=%s error=%o", value, error)
  })
}
