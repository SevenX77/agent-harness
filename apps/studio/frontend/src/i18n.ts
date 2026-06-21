import i18n from "i18next"
import LanguageDetector from "i18next-browser-languagedetector"
import { initReactI18next } from "react-i18next"
import enErrors from "./locales/en/errors.json"
import enSettings from "./locales/en/settings.json"
import zhCnErrors from "./locales/zh-CN/errors.json"
import zhCnSettings from "./locales/zh-CN/settings.json"

export const defaultNS = "settings"

export const resources = {
  en: {
    settings: enSettings,
    errors: enErrors,
  },
  "zh-CN": {
    settings: zhCnSettings,
    errors: zhCnErrors,
  },
} as const

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
        ns: ["settings", "errors"],
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
