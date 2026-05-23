import { Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { CredentialsState, RolesData } from "@/api/llm"
import type { RoleChainStatusMap } from "@/hooks/useRoleTestChainRunner"
import { appendRole, visibleRoleNames } from "../role-utils"
import { RoleCard } from "./RoleCard"

export function RoleCardList({
  data,
  credentialsByCode,
  testStatuses,
  testChainRunning,
  onRunTestChain,
  onChange,
}: {
  data: RolesData
  credentialsByCode: Record<string, CredentialsState["providers"][number]>
  testStatuses: RoleChainStatusMap
  testChainRunning: boolean
  onRunTestChain: (roleName: string) => void
  onChange: (next: RolesData) => void
}) {
  const roleNames = visibleRoleNames(data)

  return (
    <div className="space-y-4">
      {roleNames.map((roleName) => (
        <RoleCard
          key={roleName}
          data={data}
          credentialsByCode={credentialsByCode}
          roleName={roleName}
          testStatuses={testStatuses}
          testChainRunning={testChainRunning}
          onRunTestChain={() => onRunTestChain(roleName)}
          onChange={onChange}
        />
      ))}
      <Button type="button" variant="default" onClick={() => onChange(appendRole(data))} className="gap-1">
        <Plus className="size-3.5" />
        Add Role
      </Button>
    </div>
  )
}
