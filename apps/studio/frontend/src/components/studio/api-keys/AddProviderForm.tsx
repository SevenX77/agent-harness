export type AddProviderType = "third-party"
export const newProviderName = "New Provider"

export interface AddProviderFormSubmission {
  providerCode: string
  name: string
  baseUrl: string
  apiKey: string
  type: AddProviderType
}

export function providerCodeFromCustomName(customName: string): string {
  return customName.toLowerCase().replace(/[^a-z0-9]/g, "-")
}

export function createBlankAddProviderSubmission(): AddProviderFormSubmission {
  return {
    providerCode: `custom-${newProviderCodeSuffix()}`,
    name: newProviderName,
    baseUrl: "",
    apiKey: "",
    type: "third-party",
  }
}

export function deriveAddProviderFormSubmission({
  customName,
  customBaseUrl,
  apiKey,
}: {
  type?: AddProviderType
  customName: string
  customBaseUrl: string
  apiKey: string
}): AddProviderFormSubmission {
  return {
    providerCode: providerCodeFromCustomName(customName),
    name: customName,
    baseUrl: customBaseUrl,
    apiKey,
    type: "third-party",
  }
}

function newProviderCodeSuffix(): string {
  return (
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now()}-${Math.random().toString(36).slice(2)}`
  ).toString()
}
