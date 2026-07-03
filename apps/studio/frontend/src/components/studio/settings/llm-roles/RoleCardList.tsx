import { memo, useEffect, useState } from "react"
import { Cog, Plus, type LucideIcon } from "lucide-react"
import { getFixedRoleNames } from "@/api/llm"
import { Button } from "@/components/ui/button"
import {
  CatalogAccordion,
  CatalogAccordionContent,
  CatalogAccordionItem,
  CatalogAccordionTrigger,
} from "@/components/ui/catalog-accordion"
import type { CredentialsState, ModelGroup, ProviderModelOption, RoleTestResponse, RolesData } from "@/api/llm"
import type { RoleChainStatusMap } from "@/hooks/useRoleTestChainRunner"
import { appendRole, visibleRoleNames } from "../role-utils"
import { RoleCard, type RoleCategory } from "./RoleCard"
import { RoleNameDialog } from "./RoleNameDialog"
import { useLazyRenderCount } from "./useLazyRenderCount"

const rolesInitialRenderCount = 8
const rolesRenderStep = 8

export const RoleCardList = memo(function RoleCardList({
  data,
  credentialsByCode,
  modelDisplayNamesByCode,
  ownedProviderCodesByModel,
  providerModelsByRouteId,
  testStatusesByRole,
  roleTestResults,
  roleTestErrors,
  roleTestRunningByName,
  onRunTestChain,
  getActiveAvailableModelDragId,
  getAvailableModelGroup,
  onChange,
  onDeleteRole,
}: {
  data: RolesData
  credentialsByCode: Record<string, CredentialsState["providers"][number]>
  modelDisplayNamesByCode: ReadonlyMap<string, string>
  ownedProviderCodesByModel: ReadonlyMap<string, ReadonlySet<string>>
  providerModelsByRouteId: ReadonlyMap<string, ProviderModelOption>
  testStatusesByRole: Record<string, RoleChainStatusMap>
  roleTestResults: Record<string, RoleTestResponse | undefined>
  roleTestErrors: Record<string, string | undefined>
  roleTestRunningByName: Record<string, boolean | undefined>
  onRunTestChain: (roleName: string) => void
  getActiveAvailableModelDragId: () => string | null
  getAvailableModelGroup: (modelGroupId: string) => ModelGroup | null
  onChange: (next: RolesData) => void
  onDeleteRole: (roleName: string) => void
}) {
  const roleNames = visibleRoleNames(data)
  // 固定角色(引擎 builtin 硬依赖,如 md-patch 的 fast)不可删除 → 隐藏其删除入口。
  const [fixedRoleNames, setFixedRoleNames] = useState<ReadonlySet<string>>(() => new Set())
  useEffect(() => {
    let alive = true
    getFixedRoleNames()
      .then((names) => {
        if (alive) setFixedRoleNames(new Set(names))
      })
      .catch(() => {
        /* 取不到就当没有固定角色(后端仍会拒删,不影响正确性) */
      })
    return () => {
      alive = false
    }
  }, [])
  const {
    hasMore,
    sentinelRef,
    visibleCount,
  } = useLazyRenderCount({
    total: roleNames.length,
    initialCount: rolesInitialRenderCount,
    step: rolesRenderStep,
    resetKey: roleNames.join("\u0000"),
  })
  const visibleRoles = roleNames.slice(0, visibleCount)
  const roleGroups = roleCategoryGroups(data, visibleRoles, roleNames)

  return (
    <div className="space-y-4" data-lazy-list="roles">
      <CatalogAccordion
        type="multiple"
        defaultValue={["graph-agent"]}
      >
        {roleGroups.map((group) => (
          <CatalogAccordionItem
            key={group.category}
            value={group.category}
            data-role-category={group.category}
          >
            <CatalogAccordionTrigger>
              <span className="flex min-w-0 items-center gap-2">
                {group.label}
                <group.Icon aria-hidden="true" className="size-3.5 text-muted-foreground" />
              </span>
            </CatalogAccordionTrigger>
            <CatalogAccordionContent className="space-y-4 pb-5">
              {group.roles.length > 0 ? (
                group.roles.map((roleName) => (
                  <RoleCard
                    key={roleName}
                    data={data}
                    category={group.category}
                    credentialsByCode={credentialsByCode}
                    modelDisplayNamesByCode={modelDisplayNamesByCode}
                    ownedProviderCodesByModel={ownedProviderCodesByModel}
                    providerModelsByRouteId={providerModelsByRouteId}
                    roleName={roleName}
                    isFixed={fixedRoleNames.has(roleName)}
                    testStatuses={testStatusesByRole[roleName] ?? {}}
                    testChainRunning={Boolean(roleTestRunningByName[roleName])}
                    roleTestResult={roleTestResults[roleName]}
                    roleTestError={roleTestErrors[roleName]}
                    onRunTestChain={onRunTestChain}
                    getActiveAvailableModelDragId={getActiveAvailableModelDragId}
                    getAvailableModelGroup={getAvailableModelGroup}
                    onChange={onChange}
                    onDeleteRole={onDeleteRole}
                  />
                ))
              ) : (
                <div className="rounded-md border border-dashed border-border/60 bg-muted/10 px-4 py-6 text-center text-xs text-muted-foreground">
                  No {group.emptyLabel} configured.
                </div>
              )}
              <RoleNameDialog
                title={`New ${group.addTitle}`}
                initialName={group.initialRoleName}
                existingNames={roleNames}
                submitLabel="Add"
                trigger={(
                  <Button
                    type="button"
                    variant="default"
                    data-role-add-trigger="true"
                    data-role-add-category={group.category}
                    className="gap-1"
                  >
                    <Plus data-role-icon="true" className="size-3.5 text-primary-foreground/80" />
                    Add {group.addTitle}
                  </Button>
                )}
                onSubmit={(roleName) => onChange(appendRole(data, roleName))}
              />
            </CatalogAccordionContent>
          </CatalogAccordionItem>
        ))}
      </CatalogAccordion>
      {hasMore ? (
        <div
          ref={sentinelRef}
          data-lazy-sentinel="roles"
          className="h-px w-full"
          aria-hidden="true"
        />
      ) : null}
    </div>
  )
})

function roleCategoryGroups(data: RolesData, visibleRoleNames: string[], allRoleNames: string[]) {
  const groups: Array<{
    category: RoleCategory
    label: string
    emptyLabel: string
    addTitle: string
    initialRoleName: string
    Icon: LucideIcon
    roles: string[]
  }> = [
    {
      category: "graph-agent",
      label: "Graph Agent Roles",
      emptyLabel: "Graph Agent roles",
      addTitle: "Graph Agent Role",
      initialRoleName: "",
      Icon: Cog,
      roles: [],
    },
  ]
  const visibleRoleSet = new Set(visibleRoleNames)

  for (const roleName of allRoleNames) {
    if (!visibleRoleSet.has(roleName)) continue
    const category = roleCategoryForRole(data, roleName)
    if (category === "graph-agent") groups[0].roles.push(roleName)
  }

  return groups
}

function roleCategoryForRole(data: RolesData, roleName: string): RoleCategory {
  const roleKind = data.roles[roleName]?.role_kind
  if (roleKind === "copilot") return "copilot"
  if (roleKind === "graph_agent") return "graph-agent"
  return "graph-agent"
}
