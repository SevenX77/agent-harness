import type { CredentialsState, RolesData } from "../../../api/llm"

export function endpointIdFromRouteId(routeId: string): string | null {
  const separatorIndex = routeId.indexOf(":")
  if (separatorIndex <= 0) return null
  return routeId.slice(0, separatorIndex)
}

export function endpointIdForProviderCode(data: RolesData, providerCode: string): string | null {
  const configuredEndpointId = data.providers[providerCode]?.endpoint_id?.trim()
  if (configuredEndpointId) return configuredEndpointId
  return endpointIdFromRouteId(providerCode)
}

export function credentialsByProviderCode(
  data: RolesData,
  credentials: CredentialsState,
): Record<string, CredentialsState["providers"][number]> {
  const byEndpointId = Object.fromEntries(credentials.providers.map((provider) => [provider.id, provider]))
  const byProviderCode: Record<string, CredentialsState["providers"][number]> = { ...byEndpointId }
  for (const providerCode of Object.keys(data.providers)) {
    const endpointId = endpointIdForProviderCode(data, providerCode)
    const endpointCredential = endpointId ? byEndpointId[endpointId] : undefined
    if (endpointCredential) {
      byProviderCode[providerCode] = endpointCredential
    }
  }
  return byProviderCode
}
