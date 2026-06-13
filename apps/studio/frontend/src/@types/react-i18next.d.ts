import type { defaultNS, resources } from "../i18n"

declare module "*.json" {
  const value: Record<string, unknown>
  export default value
}

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: typeof defaultNS
    resources: (typeof resources)["en"]
  }
}
