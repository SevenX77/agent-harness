import { Activity, Plus, Router, Trash2 } from "lucide-react"
import type { ProviderEndpoint, ProviderImportDraft, RegistryResponse } from "@/api/llm"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { DeleteConfirmDialog } from "@/components/ui/delete-confirm-dialog"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldSet,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import { SectionTitle } from "../shared"
import { ImportDraftPanel } from "./ImportDraftPanel"

export function EndpointsTab({
  registry,
  loading,
  error,
  saveStatus,
  importDrafts,
  onAddEndpoint,
  onEndpointChange,
  onDeleteEndpoint,
  onTestEndpoint,
  onProbeRoute,
  onApplyDraft,
}: {
  registry: RegistryResponse | null
  loading: boolean
  error: string | null
  saveStatus: SaveStatus
  importDrafts: ProviderImportDraft[]
  onAddEndpoint: () => void
  onEndpointChange: (endpointId: string, patch: Partial<ProviderEndpoint>) => void
  onDeleteEndpoint: (endpointId: string) => void
  onTestEndpoint: (endpointId: string) => void
  onProbeRoute: (routeId: string) => void
  onApplyDraft: (draftId: string) => void
}) {
  const endpoints = Object.values(registry?.provider_endpoints ?? {})
  const routesByEndpoint = groupRoutesByEndpoint(registry)

  return (
    <div className="space-y-5">
      <SectionTitle
        title="Endpoints"
        description="Configure callable provider endpoints and verify their exact route inventory."
        trailing={(
          <div className="flex items-center gap-2">
            <SaveStatusBadge status={saveStatus} />
            <Button type="button" size="sm" onClick={onAddEndpoint}>
              <Plus className="size-3.5" />
              Endpoint
            </Button>
          </div>
        )}
      />

      {loading ? (
        <Card size="sm" className="rounded-md">
          <CardContent className="py-5 text-xs text-muted-foreground">Loading endpoints...</CardContent>
        </Card>
      ) : null}

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
          {error}
        </div>
      ) : null}

      {!loading && endpoints.length === 0 ? (
        <Card size="sm" className="rounded-md">
          <CardContent className="py-5 text-xs text-muted-foreground">
            No endpoints configured. Add one endpoint to start route discovery.
          </CardContent>
        </Card>
      ) : null}

      {endpoints.map((endpoint) => (
        <EndpointCard
          key={endpoint.endpoint_id}
          endpoint={endpoint}
          routes={routesByEndpoint.get(endpoint.endpoint_id) ?? []}
          onEndpointChange={onEndpointChange}
          onDeleteEndpoint={onDeleteEndpoint}
          onTestEndpoint={onTestEndpoint}
          onProbeRoute={onProbeRoute}
        />
      ))}

      <ImportDraftPanel drafts={importDrafts} onApplyDraft={onApplyDraft} />
    </div>
  )
}

function EndpointCard({
  endpoint,
  routes,
  onEndpointChange,
  onDeleteEndpoint,
  onTestEndpoint,
  onProbeRoute,
}: {
  endpoint: ProviderEndpoint
  routes: Array<RegistryResponse["provider_routes"][string]>
  onEndpointChange: (endpointId: string, patch: Partial<ProviderEndpoint>) => void
  onDeleteEndpoint: (endpointId: string) => void
  onTestEndpoint: (endpointId: string) => void
  onProbeRoute: (routeId: string) => void
}) {
  return (
    <Card size="sm" className="rounded-md">
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="break-words text-sm">{endpoint.display_name || endpoint.endpoint_id}</CardTitle>
            <p className="mt-1 break-all font-mono text-[11px] text-muted-foreground">{endpoint.endpoint_id}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Badge variant={endpoint.status === "verified" ? "default" : "secondary"}>{endpoint.status}</Badge>
            <Button type="button" size="sm" variant="outline" onClick={() => onTestEndpoint(endpoint.endpoint_id)}>
              <Activity className="size-3.5" />
              Test
            </Button>
            <DeleteConfirmDialog
              itemName={endpoint.display_name || endpoint.endpoint_id}
              description="Deleting an endpoint also requires deleting unreferenced routes that belong to it."
              onConfirm={() => onDeleteEndpoint(endpoint.endpoint_id)}
              trigger={(
                <Button type="button" size="icon" variant="ghost" aria-label={`Delete endpoint ${endpoint.endpoint_id}`}>
                  <Trash2 className="size-3.5" />
                </Button>
              )}
            />
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <FieldSet>
          <FieldGroup className="grid gap-3 md:grid-cols-2">
            <Field>
              <FieldLabel>Display Name</FieldLabel>
              <Input
                value={endpoint.display_name}
                onChange={(event) => onEndpointChange(endpoint.endpoint_id, { display_name: event.target.value })}
              />
            </Field>
            <Field>
              <FieldLabel>Protocol</FieldLabel>
              <Select
                value={endpoint.protocol}
                onValueChange={(value) => onEndpointChange(endpoint.endpoint_id, { protocol: value as ProviderEndpoint["protocol"] })}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="anthropic_compatible">Anthropic Compatible</SelectItem>
                  <SelectItem value="openai_compatible">OpenAI Compatible</SelectItem>
                  <SelectItem value="google_genai">Google GenAI</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel>Base URL</FieldLabel>
              <Input
                value={endpoint.base_url}
                onChange={(event) => onEndpointChange(endpoint.endpoint_id, { base_url: event.target.value })}
              />
            </Field>
            <Field>
              <FieldLabel>API Key</FieldLabel>
              <Input
                value={endpoint.api_key ?? ""}
                type="password"
                onChange={(event) => onEndpointChange(endpoint.endpoint_id, { api_key: event.target.value })}
              />
              <FieldDescription>Leave the redacted value unchanged to preserve the current secret.</FieldDescription>
            </Field>
          </FieldGroup>
        </FieldSet>

        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs font-medium text-foreground">
            <Router className="size-3.5 text-primary" />
            Routes
          </div>
          {routes.length === 0 ? (
            <div className="rounded-md border border-dashed border-border px-3 py-3 text-xs text-muted-foreground">
              No routes discovered for this endpoint.
            </div>
          ) : null}
          {routes.map((route) => (
            <div key={route.route_id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border/70 p-2">
              <div className="min-w-0">
                <div className="break-words text-xs font-medium text-foreground">{route.display_name}</div>
                <div className="break-all font-mono text-[11px] text-muted-foreground">{route.route_id}</div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Badge variant={route.status === "verified" ? "default" : "secondary"}>{route.status}</Badge>
                <Button type="button" size="sm" variant="outline" onClick={() => onProbeRoute(route.route_id)}>
                  Probe
                </Button>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function groupRoutesByEndpoint(registry: RegistryResponse | null): Map<string, Array<RegistryResponse["provider_routes"][string]>> {
  const grouped = new Map<string, Array<RegistryResponse["provider_routes"][string]>>()
  Object.values(registry?.provider_routes ?? {}).forEach((route) => {
    const routes = grouped.get(route.endpoint_id) ?? []
    routes.push(route)
    grouped.set(route.endpoint_id, routes)
  })
  return grouped
}

function SaveStatusBadge({ status }: { status: SaveStatus }) {
  return <Badge variant={status === "error" ? "destructive" : "secondary"}>{status}</Badge>
}
