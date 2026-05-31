import { useState } from "react"
import { FlaskConical, Loader2, Plus } from "lucide-react"
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
  initialClaudeCopilotRoleIds,
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

interface ActiveCopilotModelCard {
  id: string
  roleId: string | null
}

export function CopilotTab() {
  const claudeModelGroups = mockCopilotRoles.filter((role) => (
    role.sdkId === "claude-agent-sdk" && compatibleRoutesForRole(role).length > 0
  ))
  const [activeCards, setActiveCards] = useState<ActiveCopilotModelCard[]>(() => (
    initialClaudeCopilotRoleIds.map((roleId) => ({ id: `built-in-${roleId}`, roleId }))
  ))
  const [nextDraftIndex, setNextDraftIndex] = useState(1)
  const [testingRoleIds, setTestingRoleIds] = useState<ReadonlySet<string>>(() => new Set())
  const [routeStatusOverrides, setRouteStatusOverrides] = useState<Record<string, CopilotRouteJobStatus>>({})
  const [routeOrders, setRouteOrders] = useState<Record<string, string[]>>({})
  const selectedRoleIds = activeCards
    .map((card) => card.roleId)
    .filter(isRoleId)

  function updateRouteOrder(roleId: string, nextOrder: string[]) {
    setRouteOrders((current) => ({ ...current, [roleId]: nextOrder }))
  }

  function addDraftModelCard() {
    setActiveCards((current) => {
      if (current.some((card) => card.roleId === null)) return current
      return [...current, { id: `draft-${nextDraftIndex}`, roleId: null }]
    })
    setNextDraftIndex((current) => current + 1)
  }

  function selectModelGroup(cardId: string, roleId: string) {
    setActiveCards((current) => current.map((card) => (
      card.id === cardId ? { ...card, roleId } : card
    )))
  }

  async function testRoleRoutes(role: CopilotRolePreview) {
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
    } catch (error) {
      toast.error(copilotRoleTestErrorMessage(error, role.title))
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
        trailing={<Badge variant="outline">Mock data</Badge>}
      />

      <CatalogAccordion type="multiple" defaultValue={["claude-agent-sdk"]}>
        <CatalogAccordionItem value="claude-agent-sdk">
          <CatalogAccordionTrigger>
            Claude Agent SDK
          </CatalogAccordionTrigger>
          <CatalogAccordionContent className="-mx-2 space-y-4 pb-5">
            {activeCards.map((card) => {
              const role = card.roleId
                ? claudeModelGroups.find((candidate) => candidate.id === card.roleId)
                : null
              if (!role) {
                return (
                  <EmptyCopilotRoleCard
                    key={card.id}
                    roles={claudeModelGroups.filter((candidate) => !selectedRoleIds.includes(candidate.id))}
                    onSelectModelGroup={(roleId) => selectModelGroup(card.id, roleId)}
                  />
                )
              }
              const visibleRoutes = compatibleRoutesForRole(role)
              const routeOrder = routeOrders[role.id] ?? defaultRouteOrderForRole(role)
              const chainRoutes = routeOrder
                .map((routeId) => visibleRoutes.find((route) => route.id === routeId))
                .filter(isCopilotRoute)
              const appendableRoutes = visibleRoutes.filter((route) => !routeOrder.includes(route.id))

              return (
                <CopilotRoleCard
                  key={role.id}
                  role={role}
                  routeOrder={routeOrder}
                  chainRoutes={chainRoutes}
                  appendableRoutes={appendableRoutes}
                  routeStatusOverrides={routeStatusOverrides}
                  isTesting={testingRoleIds.has(role.id)}
                  onTest={() => testRoleRoutes(role)}
                  onUpdateRouteOrder={(nextOrder) => updateRouteOrder(role.id, nextOrder)}
                />
              )
            })}
            <Button
              type="button"
              variant="default"
              data-copilot-model-add-trigger="true"
              className="gap-1"
              onClick={addDraftModelCard}
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
  routeOrder,
  chainRoutes,
  appendableRoutes,
  routeStatusOverrides,
  isTesting,
  onTest,
  onUpdateRouteOrder,
}: {
  role: CopilotRolePreview
  routeOrder: string[]
  chainRoutes: CopilotRoutePreview[]
  appendableRoutes: CopilotRoutePreview[]
  routeStatusOverrides: Record<string, CopilotRouteJobStatus>
  isTesting: boolean
  onTest: () => void
  onUpdateRouteOrder: (nextOrder: string[]) => void
}) {
  const compatibleRoutes = compatibleRoutesForRole(role)
  const readyCount = compatibleRoutes.filter((route) => (
    (routeStatusOverrides[route.id] ?? route.agentStatus) === "ready"
  )).length

  return (
    <Card size="sm" className="min-w-0 rounded-md" data-copilot-role-card="true">
      <CardHeader className="!grid-cols-1 items-start gap-2 sm:!grid-cols-[minmax(0,1fr)_auto]">
        <div className="min-w-0">
          <CardTitle className="flex min-w-0 flex-wrap items-center gap-2">
            {role.title}
            <Badge variant="secondary">{role.source === "built_in" ? "Built-in" : "Third-party"}</Badge>
          </CardTitle>
          <CardDescription>{role.description}</CardDescription>
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
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        <CopilotModelGroupCard
          modelName={role.modelLabel}
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
  roles,
  onSelectModelGroup,
}: {
  roles: CopilotRolePreview[]
  onSelectModelGroup: (roleId: string) => void
}) {
  return (
    <Card
      size="sm"
      className="min-w-0 rounded-md border-dashed bg-card/70"
      data-copilot-empty-role-card="true"
      data-copilot-role-card="true"
    >
      <CardHeader className="!grid-cols-1 items-start gap-2">
        <div className="min-w-0">
          <CardTitle>New Claude model</CardTitle>
          <CardDescription>Select a compatible model group to create this copilot role.</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <FieldGroup>
          <Field orientation="responsive" className="items-start">
            <FieldContent>
              <FieldLabel>Model group</FieldLabel>
              <FieldDescription>Only groups with Anthropic-compatible routes are listed.</FieldDescription>
            </FieldContent>
            <Select onValueChange={onSelectModelGroup} disabled={roles.length === 0}>
              <SelectTrigger
                size="sm"
                className="w-full min-w-0 sm:w-64"
                data-copilot-model-group-select="true"
              >
                <SelectValue placeholder={roles.length > 0 ? "Choose model group" : "No compatible model groups"} />
              </SelectTrigger>
              <SelectContent>
                {roles.map((role) => (
                  <SelectItem key={role.id} value={role.id} data-copilot-model-option={role.id}>
                    {role.modelLabel}
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

function defaultRouteOrderForRole(role: CopilotRolePreview): string[] {
  const compatibleRouteIds = new Set(compatibleRoutesForRole(role).map((route) => route.id))
  return role.activeRouteIds.filter((routeId) => compatibleRouteIds.has(routeId))
}

function isRoleId(roleId: string | null): roleId is string {
  return typeof roleId === "string"
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
