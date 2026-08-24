import i18n from "i18next"
import LanguageDetector from "i18next-browser-languagedetector"
import { initReactI18next } from "react-i18next"
import { namespaceResources } from "./i18n/namespaces"

export const defaultNS = "settings"

// The namespace → bundle mapping lives in `./i18n/namespaces.ts` — the single
// explicit registry every namespace (centralized or module-co-located) is
// added to by name. This file only wires that registry into i18next.
export const resources = namespaceResources

export const supportedLngs = ["en", "zh-CN"] as const
export type SupportedLanguage = (typeof supportedLngs)[number]

export const i18nReady = i18n.isInitialized
  ? Promise.resolve(i18n)
  : i18n
      .use(LanguageDetector)
      .use(initReactI18next)
      .init({
        resources,
        defaultNS,
        fallbackLng: "en",
        supportedLngs,
        load: "currentOnly",
        ns: Object.keys(resources.en),
        detection: {
          order: ["localStorage"],
          caches: ["localStorage"],
          lookupLocalStorage: "studio.language",
        },
        interpolation: {
          escapeValue: false,
        },
        initAsync: false,
        returnNull: false,
      })

export default i18n
