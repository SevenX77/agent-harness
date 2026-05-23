import { useMemo, type ReactNode } from "react"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import { useRoleTestChainRunner } from "@/hooks/useRoleTestChainRunner"
import type { CredentialsState, RolesData } from "../../../api/llm"
import { AvailableModelsSidebar } from "./llm-roles/AvailableModelsSidebar"
import { RoleSaveStatusBadge } from "./llm-roles/RoleBadges"
import { RoleCardList } from "./llm-roles/RoleCardList"
import { SectionTitle } from "./shared"

export { ModelSettingsDialog, ModelSettingsFields } from "./llm-roles/ModelSettingsDialog"

export function LlmRolesTab({
  data,
  credentials,
  saveStatus,
  error,
  onChange,
}: {
  data: RolesData | null
  credentials: CredentialsState
  saveStatus: SaveStatus
  error: string | null
  onChange: (next: RolesData) => void
}) {
  const credentialsByCode = useMemo(
    () => Object.fromEntries(credentials.providers.map((provider) => [provider.id, provider])),
    [credentials.providers],
  )
  const { isRunning: testChainRunning, run: runTestChain, statuses: testStatuses } = useRoleTestChainRunner()

  if (!data) {
    return (
      <LlmRolesLayout sidebar={<LlmRolesModelsSkeleton />}>
        <SectionTitle title="LLM Roles" description="Edit active models and fallback order." />
        <LlmRolesRolesSkeleton />
      </LlmRolesLayout>
    )
  }

  return (
    <LlmRolesLayout sidebar={<AvailableModelsSidebar credentials={credentials} />}>
      <SectionTitle
        title="LLM Roles"
        description="Edit active models and fallback order. Changes auto-save."
        trailing={<RoleSaveStatusBadge status={saveStatus} />}
      />

      {error ? <div className="mb-3 text-xs text-destructive">Validation failed: {error}</div> : null}

      <RoleCardList
        data={data}
        credentialsByCode={credentialsByCode}
        testStatuses={testStatuses}
        testChainRunning={testChainRunning}
        onRunTestChain={(roleName) => void runTestChain({ data, roleName, credentials })}
        onChange={onChange}
      />
    </LlmRolesLayout>
  )
}

function LlmRolesLayout({ children, sidebar }: { children: ReactNode; sidebar: ReactNode }) {
  return (
    <div className="grid min-h-full min-w-0 gap-4 lg:h-full lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_minmax(14rem,20vw)] lg:grid-rows-[minmax(0,1fr)] lg:overflow-hidden 2xl:grid-cols-[minmax(0,1fr)_minmax(14rem,18rem)]">
      <ScrollArea className="min-h-0 min-w-0 overflow-hidden lg:h-full">
        <div className="pr-2">
          {children}
        </div>
      </ScrollArea>
      {sidebar}
    </div>
  )
}

function LlmRolesRolesSkeleton() {
  return (
    <div className="space-y-4">
      <Card size="sm" className="rounded-md">
        <CardHeader>
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-72 max-w-full" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
      <Card size="sm" className="rounded-md">
        <CardHeader>
          <Skeleton className="h-5 w-36" />
          <Skeleton className="h-4 w-64 max-w-full" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    </div>
  )
}

function LlmRolesModelsSkeleton() {
  return (
    <aside className="min-w-0 lg:sticky lg:top-0 lg:h-full lg:min-h-0 lg:self-start">
      <div className="flex min-h-0 flex-col gap-3 lg:h-full">
        <div className="space-y-2">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-8 w-full" />
        </div>
        <div className="space-y-3">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      </div>
    </aside>
  )
}
