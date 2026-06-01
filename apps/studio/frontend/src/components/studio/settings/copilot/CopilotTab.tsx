import { useMemo, useState } from "react"
import { FlaskConical, Loader2, Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  CatalogAccordion,
  CatalogAccordionContent,
  CatalogAccordionItem,
  CatalogAccordionTrigger,
} from "@/components/ui/catalog-accordion"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { requestDeleteConfirmationToast } from "@/components/ui/delete-confirm-toast"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { SectionTitle } from "../shared"
import { CopilotModelGroupCard } from "./CopilotModelGroupCard"
import {
  isClaudeAgentSdkCompatibleRoute,
  mockCopilotRoles,
  type CopilotRolePreview,
  type CopilotRoutePreview,
} from "./mock-copilot-data"
import {
  copilotRoleTestErrorMessage,
  copilotRouteStatusesFromJob,
  runCopilotRoleTestJob,
  type CopilotRouteJobStatus,
} from "./copilot-role-test"
import type { CredentialsState, ModelGroup, RolesData } from "@/api/llm"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"

export function CopilotTab({
  data = null,
  credentials = { providers: [] },
  modelGroups = [],
  onChange = () => {},
  saveStatus = "idle",
  error = null,
}: {
  data?: RolesData | null
  credentials?: CredentialsState
  modelGroups?: ModelGroup[]
  onChange?: (next: RolesData) => void
  saveStatus?: SaveStatus
  error?: string | null
} = {}) {
  void credentials
  void modelGroups
  void saveStatus
  void error

  const claudeModelGroups = mockCopilotRoles.filter((role) => (
    role.sdkId === "claude-agent-sdk" && compatibleRoutesForRole(role).length > 0
  ))

  const activeRoles = useMemo(() => {
    const filtered = data
      ? Object.entries(data.roles)
          .filter(([name]) => name === "copilot_opus_4_7" || name === "copilot_deepseek_v4" || name === "sonnet-4-7-third-party" || name.startsWith("copilot_custom_"))
          .map(([name, role]) => {
            const mockData = mockCopilotRoles.find((r) => r.id === name)
            return {
              id: name,
              title: mockData?.title ?? name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()),
              description: mockData?.description ?? "Coding copilot role.",
              source: mockData?.source ?? ("third_party" as const),
              modelGroupId: mockData?.id ?? name,
              fallback_chain: role.fallback_chain ?? [],
            }
          })
      : []

    if (filtered.length === 0) {
      return mockCopilotRoles.slice(0, 2).map((mockData) => ({
        id: mockData.id,
        title: mockData.title,
        description: mockData.description,
        source: mockData.source,
        modelGroupId: mockData.id,
        fallback_chain: mockData.activeRouteIds.map((routeId) => ({ route_id: routeId, runtime_settings: {} })),
      }))
    }
    return filtered
  }, [data])

  const [testingRoleIds, setTestingRoleIds] = useState<ReadonlySet<string>>(() => new Set())
  const [routeStatusOverrides, setRouteStatusOverrides] = useState<Record<string, CopilotRouteJobStatus>>({})

  const selectedModelGroupIds = new Set(
    activeRoles.map((role) => role.modelGroupId).filter((id): id is string => typeof id === "string" && id !== null),
  )
  const modelGroupOptions = claudeModelGroups.filter((modelGroup) => !selectedModelGroupIds.has(modelGroup.id))

  function updateRouteOrder(roleId: string, nextOrder: string[]) {
    if (!data) return
    const nextRoles = { ...data.roles }
    const role = nextRoles[roleId]
    if (!role) return
    nextRoles[roleId] = {
      ...role,
      fallback_chain: nextOrder.map((routeId) => ({
        route_id: routeId,
        runtime_settings: {},
      })),
    }
    onChange({ ...data, roles: nextRoles })
  }

  function addDraftCopilotRole() {
    if (!data) return
    const nextIndex = Object.keys(data.roles).filter(k => k.startsWith("copilot_custom_")).length + 1
    const newRoleId = `copilot_custom_${nextIndex}`
    const nextRoles = {
      ...data.roles,
      [newRoleId]: {
        role_kind: "copilot" as const,
        system_prompt_prefix: "",
        model_fallback_enabled: true,
        fallback_chain: [],
        intent: { provider_preference: "manual_order" as const },
        model_groups: [],
        active_model: "",
        models: {},
      }
    }
    onChange({ ...data, roles: nextRoles })
  }

  function selectModelGroup(roleId: string, modelGroupId: string) {
    if (!data) return
    const modelGroup = claudeModelGroups.find((candidate) => candidate.id === modelGroupId)
    if (!modelGroup) return
    const nextRoles = { ...data.roles }
    const role = nextRoles[roleId]
    if (!role) return

    const defaultRouteIds = modelGroup.activeRouteIds.filter((routeId) =>
      modelGroup.availableRoutes.filter(isClaudeAgentSdkCompatibleRoute).some((r) => r.id === routeId)
    )

    delete nextRoles[roleId]
    nextRoles[modelGroupId] = {
      role_kind: "copilot" as const,
      system_prompt_prefix: "",
      model_fallback_enabled: true,
      fallback_chain: defaultRouteIds.map((routeId) => ({
        route_id: routeId,
        runtime_settings: {},
      })),
      intent: { provider_preference: "manual_order" as const },
      model_groups: [],
      active_model: "",
      models: {},
    }
    onChange({ ...data, roles: nextRoles })
  }

  function requestDeleteCopilotRole(role: { id: string; title: string }) {
    requestDeleteConfirmationToast({
      id: `delete-copilot-role-${role.id}`,
      title: `Delete ${role.title}?`,
      description: "Remove this Copilot role permanently.",
      onConfirm: () => {
        if (!data) return
        const nextRoles = { ...data.roles }
        delete nextRoles[role.id]
        onChange({ ...data, roles: nextRoles })
      },
    })
  }

  async function testRoleRoutes(role: { id: string; title: string }) {
    setTestingRoleIds((current) => {
      const next = new Set(current)
      next.add(role.id)
      return next
    })
    try {
      const result = await runCopilotRoleTestJob(role.id, {
        onProgress: (job) => {
          setRouteStatusOverrides((current) => ({
            ...current,
            ...copilotRouteStatusesFromJob(job),
          }))
        },
      })
      if (result.status === "ok") {
        toast.success(`${role.title} test passed`)
      } else {
        toast.warning(`${role.title} test needs attention`)
      }
    } catch (err) {
      toast.error(copilotRoleTestErrorMessage(err, role.title))
    } finally {
      setTestingRoleIds((current) => {
        const next = new Set(current)
        next.delete(role.id)
        return next
      })
    }
  }

  return (
    <div data-copilot-settings-page="true" className="max-w-3xl min-w-0">
      <SectionTitle
        title="Copilot"
        description="Configure copilot roles with the same model group fallback pattern used by LLM Roles."
        trailing={<Badge variant="outline">Backend Integration</Badge>}
      />

      <CatalogAccordion type="multiple" defaultValue={["claude-agent-sdk"]}>
        <CatalogAccordionItem value="claude-agent-sdk">
          <CatalogAccordionTrigger>
            Claude Agent SDK
          </CatalogAccordionTrigger>
          <CatalogAccordionContent className="-mx-2 space-y-4 pb-5">
            {activeRoles.map((role) => {
              const modelGroup = role.modelGroupId
                ? claudeModelGroups.find((candidate) => candidate.id === role.modelGroupId)
                : null
              if (!modelGroup) {
                return (
                  <EmptyCopilotRoleCard
                    key={role.id}
                    role={role}
                    modelGroups={modelGroupOptions}
                    onSelectModelGroup={(modelGroupId) => selectModelGroup(role.id, modelGroupId)}
                    onDeleteRole={() => requestDeleteCopilotRole(role)}
                  />
                )
              }
              const visibleRoutes = compatibleRoutesForRole(modelGroup)
              const routeOrder = role.fallback_chain.map((entry) => entry.route_id)
              const chainRoutes = routeOrder
                .map((routeId) => visibleRoutes.find((route) => route.id === routeId))
                .filter(isCopilotRoute)
              const appendableRoutes = visibleRoutes.filter((route) => !routeOrder.includes(route.id))

              return (
                <CopilotRoleCard
                  key={role.id}
                  role={role}
                  modelGroup={modelGroup}
                  routeOrder={routeOrder}
                  chainRoutes={chainRoutes}
                  appendableRoutes={appendableRoutes}
                  routeStatusOverrides={routeStatusOverrides}
                  isTesting={testingRoleIds.has(role.id)}
                  onTest={() => testRoleRoutes(role)}
                  onDeleteRole={() => requestDeleteCopilotRole(role)}
                  onUpdateRouteOrder={(nextOrder) => updateRouteOrder(role.id, nextOrder)}
                />
              )
            })}
            <Button
              type="button"
              variant="default"
              data-copilot-model-add-trigger="true"
              className="gap-1"
              onClick={addDraftCopilotRole}
            >
              <Plus data-role-icon="true" className="size-3.5 text-primary-foreground/80" />
              Add model
            </Button>
          </CatalogAccordionContent>
        </CatalogAccordionItem>
      </CatalogAccordion>
    </div>
  )
}

function CopilotRoleCard({
  role,
  modelGroup,
  routeOrder,
  chainRoutes,
  appendableRoutes,
  routeStatusOverrides,
  isTesting,
  onTest,
  onDeleteRole,
  onUpdateRouteOrder,
}: {
  role: { id: string; title: string; source: "built_in" | "third_party" }
  modelGroup: CopilotRolePreview
  routeOrder: string[]
  chainRoutes: CopilotRoutePreview[]
  appendableRoutes: CopilotRoutePreview[]
  routeStatusOverrides: Record<string, CopilotRouteJobStatus>
  isTesting: boolean
  onTest: () => void
  onDeleteRole: () => void
  onUpdateRouteOrder: (nextOrder: string[]) => void
}) {
  const compatibleRoutes = compatibleRoutesForRole(modelGroup)
  const readyCount = compatibleRoutes.filter((route) => (
    (routeStatusOverrides[route.id] ?? route.agentStatus) === "ready"
  )).length

  return (
    <Card
      size="sm"
      className="min-w-0 rounded-md"
      data-copilot-role-card="true"
      data-copilot-role-source={role.source}
    >
      <CardHeader className="!grid-cols-1 items-start gap-2 sm:!grid-cols-[minmax(0,1fr)_auto]">
        <div className="min-w-0">
          <CardTitle className="flex min-w-0 flex-wrap items-center gap-2">
            {role.title}
            <Badge variant="secondary">{role.source === "built_in" ? "Built-in" : "Third-party"}</Badge>
          </CardTitle>
          <CardDescription>Coding copilot role synced with backend fallback chain.</CardDescription>
        </div>
        <CardAction className="row-start-2 flex flex-wrap items-center gap-2 justify-self-start sm:row-start-1 sm:justify-self-end">
          <Badge variant={readyCount === compatibleRoutes.length ? "success" : "outline"}>
            {readyCount}/{compatibleRoutes.length} SDK Ready
          </Badge>
          <Button
            type="button"
            variant="default"
            size="sm"
            data-copilot-test-chain="true"
            onClick={onTest}
            disabled={isTesting}
          >
            {isTesting ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <FlaskConical data-icon="inline-start" />}
            {isTesting ? "Testing" : "Test"}
          </Button>
          {role.source === "third_party" ? (
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={`Delete ${role.title}`}
              data-copilot-role-delete-trigger="true"
              className="text-muted-foreground hover:text-destructive"
              onClick={onDeleteRole}
            >
              <Trash2 data-role-icon="true" className="size-4" />
            </Button>
          ) : null}
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        <CopilotModelGroupCard
          modelName={modelGroup.modelLabel}
          modelIndex={0}
          routes={chainRoutes}
          appendableRoutes={appendableRoutes}
          routeStatusOverrides={routeStatusOverrides}
          onAddRoute={(routeId) => onUpdateRouteOrder([...routeOrder, routeId])}
          onRemoveRoute={(routeId) => onUpdateRouteOrder(routeOrder.filter((candidate) => candidate !== routeId))}
          onReorderRoutes={(activeRouteId, overRouteId) => {
            const activeIndex = routeOrder.indexOf(activeRouteId)
            const overIndex = routeOrder.indexOf(overRouteId)
            if (activeIndex < 0 || overIndex < 0) return
            onUpdateRouteOrder(moveItem(routeOrder, activeIndex, overIndex))
          }}
        />
      </CardContent>
    </Card>
  )
}

function EmptyCopilotRoleCard({
  role,
  modelGroups,
  onSelectModelGroup,
  onDeleteRole,
}: {
  role: { id: string; title: string; source: "built_in" | "third_party" }
  modelGroups: CopilotRolePreview[]
  onSelectModelGroup: (modelGroupId: string) => void
  onDeleteRole: () => void
}) {
  return (
    <Card
      size="sm"
      className="min-w-0 rounded-md border-dashed bg-card/70"
      data-copilot-empty-role-card="true"
      data-copilot-role-card="true"
      data-copilot-role-source={role.source}
    >
      <CardHeader className="!grid-cols-1 items-start gap-2 sm:!grid-cols-[minmax(0,1fr)_auto]">
        <div className="min-w-0">
          <CardTitle className="flex min-w-0 flex-wrap items-center gap-2">
            {role.title}
            <Badge variant="secondary">Third-party</Badge>
          </CardTitle>
          <CardDescription>Select one model group to configure the Copilot fallback chain.</CardDescription>
        </div>
        <CardAction className="row-start-2 justify-self-start sm:row-start-1 sm:justify-self-end">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`Delete ${role.title}`}
            data-copilot-role-delete-trigger="true"
            className="text-muted-foreground hover:text-destructive"
            onClick={onDeleteRole}
          >
            <Trash2 data-role-icon="true" className="size-4" />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        <FieldGroup>
          <Field orientation="responsive" className="items-start">
            <FieldContent>
              <FieldLabel>Model group</FieldLabel>
              <FieldDescription>Only groups with Anthropic-compatible routes are listed.</FieldDescription>
            </FieldContent>
            <Select onValueChange={onSelectModelGroup} disabled={modelGroups.length === 0}>
              <SelectTrigger
                size="sm"
                className="w-full min-w-0 sm:w-64"
                data-copilot-model-group-select="true"
              >
                <SelectValue placeholder={modelGroups.length > 0 ? "Choose model group" : "No compatible model groups"} />
              </SelectTrigger>
              <SelectContent>
                {modelGroups.map((modelGroup) => (
                  <SelectItem key={modelGroup.id} value={modelGroup.id} data-copilot-model-option={modelGroup.id}>
                    {modelGroup.modelLabel}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </FieldGroup>
      </CardContent>
    </Card>
  )
}

function compatibleRoutesForRole(role: CopilotRolePreview): CopilotRoutePreview[] {
  return role.availableRoutes.filter(isClaudeAgentSdkCompatibleRoute)
}

function isCopilotRoute(route: CopilotRoutePreview | undefined): route is CopilotRoutePreview {
  return Boolean(route)
}

function moveItem<T>(items: readonly T[], fromIndex: number, toIndex: number): T[] {
  const next = [...items]
  const [item] = next.splice(fromIndex, 1)
  next.splice(toIndex, 0, item)
  return next
}
