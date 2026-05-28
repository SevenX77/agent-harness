import { useCallback, useState } from "react"
import {
  testProviderEndpoint,
  type CredentialsState,
  type ProviderTestRequest,
  type ProviderTestResponse,
  type ProviderTestStatus,
  type RolesData,
} from "@/api/llm"
import { credentialsByProviderCode } from "@/components/studio/settings/route-credentials"

export type RoleChainStatus = ProviderTestStatus | "testing" | "idle"
type RoleProviderTestFn = (
  request: ProviderTestRequest & { model_id: string }
) => Promise<ProviderTestResponse>

export interface RoleTestTarget {
  modelCode: string
  providerCode: string
  modelId: string
  credential: CredentialsState["providers"][number] | null
}

export type RoleChainStatusMap = Record<string, { status: RoleChainStatus; message?: string }>

export function roleChainStatusKey(modelCode: string, providerCode: string): string {
  return `${modelCode}:${providerCode}`
}

export function buildRoleTestTargets(
  data: RolesData,
  roleName: string,
  credentials: CredentialsState,
): RoleTestTarget[][] {
  const role = data.roles[roleName]
  if (!role) return []
  const credentialsByCode = credentialsByProviderCode(data, credentials)
  return Object.entries(role.models).map(([modelCode, roleModel]) => (
    roleModel.providers.map((providerCode) => ({
      modelCode,
      providerCode,
      modelId: data.models[modelCode]?.providers[providerCode] ?? modelCode,
      credential: credentialsByCode[providerCode] ?? null,
    }))
  ))
}

export async function runWithConcurrency<T>(
  items: T[],
  limit: number,
  worker: (item: T) => Promise<void>,
): Promise<void> {
  const queue = [...items]
  const workers = Array.from({ length: Math.min(limit, queue.length) }, async () => {
    while (queue.length > 0) {
      const next = queue.shift()
      if (next !== undefined) {
        await worker(next)
      }
    }
  })
  await Promise.all(workers)
}

export async function runRoleTestTargets(
  modelChains: RoleTestTarget[][],
  limit: number,
  worker: (target: RoleTestTarget) => Promise<void>,
): Promise<void> {
  await runWithConcurrency(modelChains.flat(), limit, worker)
}

export function useRoleTestChainRunner({
  testFn = testProviderEndpoint,
}: {
  testFn?: RoleProviderTestFn
} = {}) {
  const [isRunning, setIsRunning] = useState(false)
  const [statuses, setStatuses] = useState<RoleChainStatusMap>({})

  const setTargetStatus = useCallback((target: RoleTestTarget, status: RoleChainStatus, message?: string) => {
    setStatuses((current) => ({
      ...current,
      [roleChainStatusKey(target.modelCode, target.providerCode)]: { status, message },
    }))
  }, [])

  const run = useCallback(
    async ({
      data,
      roleName,
      credentials,
    }: {
      data: RolesData
      roleName: string
      credentials: CredentialsState
    }) => {
      const modelChains = buildRoleTestTargets(data, roleName, credentials)
      setIsRunning(true)
      try {
        await runRoleTestTargets(modelChains, 4, async (target) => {
          if (!target.credential?.api_key.trim() || !target.credential.provider_type) {
            setTargetStatus(target, "missing_api_key", "Provider has no API key or protocol.")
            return
          }
          setTargetStatus(target, "testing")
          const response: ProviderTestResponse = await testFn({
            id: target.credential.id,
            provider_type: target.credential.provider_type,
            api_key: target.credential.api_key.trim(),
            base_url: target.credential.base_url || undefined,
            model_id: target.modelId,
          })
          setTargetStatus(target, response.status, response.message ?? undefined)
        })
      } finally {
        setIsRunning(false)
      }
    },
    [setTargetStatus, testFn],
  )

  return { isRunning, run, statuses }
}
