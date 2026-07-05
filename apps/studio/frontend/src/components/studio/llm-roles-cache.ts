import { useCallback } from "react"
import { mutate } from "swr"
import { getRoles, type RolesData } from "@/api/llm"
import { useStudioEventStream } from "@/hooks/useStudioEventStream"

export const LLM_ROLES_SWR_KEY = "llm/roles"

export function syncLlmRolesCache(next: RolesData): Promise<RolesData | undefined> {
  return mutate<RolesData>(LLM_ROLES_SWR_KEY, next, { revalidate: false })
}

export async function refreshLlmRolesCache(): Promise<RolesData> {
  const next = await getRoles({ force: true })
  await syncLlmRolesCache(next)
  return next
}

export function useLlmRolesCacheEventSync(enabled = true): void {
  const refreshRoles = useCallback(() => {
    void refreshLlmRolesCache()
  }, [])
  const ignoreRegistry = useCallback(() => {}, [])

  useStudioEventStream(
    {
      onRegistryChanged: ignoreRegistry,
      onRolesChanged: refreshRoles,
    },
    { enabled },
  )
}
