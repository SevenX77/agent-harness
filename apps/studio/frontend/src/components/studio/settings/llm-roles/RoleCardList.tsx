import { Bot, Cog, Plus, type LucideIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  CatalogAccordion,
  CatalogAccordionContent,
  CatalogAccordionItem,
  CatalogAccordionTrigger,
} from "@/components/ui/catalog-accordion"
import type { CredentialsState, ModelGroup, RolesData } from "@/api/llm"
import type { RoleChainStatusMap } from "@/hooks/useRoleTestChainRunner"
import { appendRole, visibleRoleNames } from "../role-utils"
import { RoleCard, type RoleCategory } from "./RoleCard"
import { RoleNameDialog } from "./RoleNameDialog"
import { useLazyRenderCount } from "./useLazyRenderCount"

const rolesInitialRenderCount = 8
const rolesRenderStep = 8

export function RoleCardList({
  data,
  credentialsByCode,
  testStatuses,
  testChainRunning,
  onRunTestChain,
  getActiveAvailableModelDragId,
  getAvailableModelGroup,
  onChange,
}: {
  data: RolesData
  credentialsByCode: Record<string, CredentialsState["providers"][number]>
  testStatuses: RoleChainStatusMap
  testChainRunning: boolean
  onRunTestChain: (roleName: string) => void
  getActiveAvailableModelDragId: () => string | null
  getAvailableModelGroup: (modelGroupId: string) => ModelGroup | null
  onChange: (next: RolesData) => void
}) {
  const roleNames = visibleRoleNames(data)
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
        defaultValue={["graph-agent", "copilot"]}
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
            <CatalogAccordionContent className="-mx-2 space-y-4 pb-5">
              {group.roles.length > 0 ? (
                group.roles.map((roleName) => (
                  <RoleCard
                    key={roleName}
                    data={data}
                    category={group.category}
                    credentialsByCode={credentialsByCode}
                    roleName={roleName}
                    testStatuses={testStatuses}
                    testChainRunning={testChainRunning}
                    onRunTestChain={() => onRunTestChain(roleName)}
                    getActiveAvailableModelDragId={getActiveAvailableModelDragId}
                    getAvailableModelGroup={getAvailableModelGroup}
                    onChange={onChange}
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
}

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
    {
      category: "copilot",
      label: "Copilot Roles",
      emptyLabel: "Copilot roles",
      addTitle: "Copilot Role",
      initialRoleName: "copilot_",
      Icon: Bot,
      roles: [],
    },
  ]
  const visibleRoleSet = new Set(visibleRoleNames)

  for (const roleName of allRoleNames) {
    if (!visibleRoleSet.has(roleName)) continue
    const category = roleCategoryForRole(data, roleName)
    groups.find((group) => group.category === category)?.roles.push(roleName)
  }

  return groups
}

function roleCategoryForRole(data: RolesData, roleName: string): RoleCategory {
  const roleKind = data.roles[roleName]?.role_kind
  if (roleKind === "copilot") return "copilot"
  if (roleKind === "graph_agent") return "graph-agent"
  return /copilot/i.test(roleName) ? "copilot" : "graph-agent"
}
