import { useCallback, useState } from "react"
import {
  probeRoute,
  type ProviderRoute,
  type RegistryResponse,
  type RoleEntry,
  type RolesData,
  type RouteProbeRequest,
  type RouteStatus,
} from "@/api/llm"

export type RoleChainStatus = RouteStatus | "testing" | "idle" | "missing_route" | "probe_error"

export interface RoleProbeTarget {
  roleName: string
  routeId: string
  route: ProviderRoute | null
  capabilities: string[]
}

export type RoleChainStatusMap = Record<string, { status: RoleChainStatus; message?: string }>

export function roleChainStatusKey(roleName: string, routeId: string): string {
  return `${roleName}:${routeId}`
}

export function requiredProbeCapabilities(role: RoleEntry): string[] {
  return Object.entries(role.lint_requirements)
    .filter(([, severity]) => severity !== "off")
    .map(([capability]) => capability)
}

export function buildRoleProbeTargets(
  data: RolesData,
  roleName: string,
  registry: RegistryResponse,
): RoleProbeTarget[] {
  const role = data.roles[roleName]
  if (!role) return []
  const capabilities = requiredProbeCapabilities(role)
  return role.fallback_chain.map((entry) => ({
    roleName,
    routeId: entry.route_id,
    route: registry.provider_routes[entry.route_id] ?? null,
    capabilities,
  }))
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

export function useRoleTestChainRunner({
  probeFn = probeRoute,
}: {
  probeFn?: (routeId: string, request: RouteProbeRequest) => Promise<ProviderRoute>
} = {}) {
  const [isRunning, setIsRunning] = useState(false)
  const [statuses, setStatuses] = useState<RoleChainStatusMap>({})

  const setTargetStatus = useCallback((target: RoleProbeTarget, status: RoleChainStatus, message?: string) => {
    setStatuses((current) => ({
      ...current,
      [roleChainStatusKey(target.roleName, target.routeId)]: { status, message },
    }))
  }, [])

  const run = useCallback(
    async ({
      data,
      roleName,
      registry,
    }: {
      data: RolesData
      roleName: string
      registry: RegistryResponse
    }) => {
      const targets = buildRoleProbeTargets(data, roleName, registry)
      setIsRunning(true)
      try {
        await runWithConcurrency(targets, 3, async (target) => {
          if (!target.route) {
            setTargetStatus(target, "missing_route", "Route is not present in the active registry.")
            return
          }
          setTargetStatus(target, "testing")
          try {
            const response = await probeFn(target.routeId, { capabilities: target.capabilities })
            setTargetStatus(target, response.status, response.display_name)
          } catch (error) {
            const message = error instanceof Error ? error.message : "Route probe failed."
            setTargetStatus(target, "probe_error", message)
          }
        })
      } finally {
        setIsRunning(false)
      }
    },
    [probeFn, setTargetStatus],
  )

  return { isRunning, run, statuses }
}
