import { useMemo } from "react"
import { Check, Loader2, Plus, TriangleAlert } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  CatalogAccordion,
  CatalogAccordionContent,
  CatalogAccordionItem,
  CatalogAccordionTrigger,
} from "@/components/ui/catalog-accordion"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import { createBlankAddProviderSubmission, ProviderCard, ProviderListSkeleton } from "../../api-keys"
import { officialProviderDrafts, thirdPartyProviderDrafts, notableProviderKeyForDraft, shouldShowManualModelPanel } from "../provider-utils"
import { SectionTitle } from "../shared"
import type { SettingsPageContentProps } from "../types"

function SaveStatusBadge({ status }: { status: SaveStatus }) {
  if (status === "idle") return null
  if (status === "pending") {
    return (
      <Badge variant="outline" className="gap-1 text-[10px] font-normal text-muted-foreground">
        <Loader2 className="size-3 animate-spin" />
        Pending
      </Badge>
    )
  }
  if (status === "saving") {
    return (
      <Badge variant="outline" className="gap-1 text-[10px] font-normal text-muted-foreground">
        <Loader2 className="size-3 animate-spin" />
        Saving
      </Badge>
    )
  }
  if (status === "saved") {
    return (
      <Badge variant="outline" className="gap-1 text-[10px] font-normal">
        <Check className="size-3" />
        Saved
      </Badge>
    )
  }
  // error
  return (
    <Badge variant="outline" className="gap-1 text-[10px] font-normal">
      <TriangleAlert className="size-3" />
      Save failed
    </Badge>
  )
}

export function ApiKeysTab({
  credentials,
  credentialsLoading,
  credentialsError,
  drafts,
  saveStatus,
  onProviderFieldChange,
  onGetProviderModels,
  onTestProviderEndpoint,
  onDeleteProvider,
  onAddProvider,
  onProviderModelsUpdated,
}: Pick<
  SettingsPageContentProps,
  | "credentials"
  | "credentialsLoading"
  | "credentialsError"
  | "drafts"
  | "saveStatus"
  | "onProviderFieldChange"
  | "onGetProviderModels"
  | "onTestProviderEndpoint"
  | "onDeleteProvider"
  | "onAddProvider"
  | "onProviderModelsUpdated"
>) {
  const persistedById = useMemo(
    () => Object.fromEntries(credentials.providers.map((provider) => [provider.id, provider])),
    [credentials.providers],
  )
  const officialDrafts = useMemo(() => officialProviderDrafts(drafts), [drafts])
  const thirdPartyDrafts = useMemo(() => thirdPartyProviderDrafts(drafts), [drafts])

  return (
    <div className="max-w-3xl">
      <SectionTitle
        title="API Keys"
        description="Local LLM provider credentials used by Studio runtime. Changes auto-save."
        trailing={<SaveStatusBadge status={saveStatus} />}
      />
      <div className="space-y-4" data-testid="api-keys-list">
        {credentialsLoading ? (
          <ProviderListSkeleton count={5} />
        ) : credentialsError ? (
          <Alert variant="destructive">
            <TriangleAlert className="size-3.5" />
            <AlertTitle>API Keys load failed</AlertTitle>
            <AlertDescription>
              {credentialsError}. Stored provider values are not shown until the credentials document loads.
            </AlertDescription>
          </Alert>
        ) : (
          <CatalogAccordion
            type="multiple"
            defaultValue={["official", "third-party"]}
          >
            <CatalogAccordionItem value="official">
              <CatalogAccordionTrigger>
                Official Providers
              </CatalogAccordionTrigger>
              <CatalogAccordionContent className="-mx-2 space-y-3 pb-5">
                {officialDrafts.map((draft) => {
                  const persisted = persistedById[draft.id] ?? null
                  return (
                    <ProviderCard
                      key={draft.id}
                      draft={draft}
                      persisted={persisted}
                      onFieldChange={(patch) => onProviderFieldChange(draft.id, { ...draft, ...patch })}
                      onGetModels={() => onGetProviderModels(draft.id)}
                      onEndpointTest={(modelId) => onTestProviderEndpoint(draft.id, modelId)}
                      onDelete={() => onDeleteProvider(draft.id)}
                      providerKind="official"
                      showManualModelPanel={shouldShowManualModelPanel(draft, persisted)}
                      notableProviderKey={notableProviderKeyForDraft(draft)}
                      onModelsUpdated={(models) => onProviderModelsUpdated(draft.id, models)}
                    />
                  )
                })}
              </CatalogAccordionContent>
            </CatalogAccordionItem>

            <CatalogAccordionItem value="third-party">
              <CatalogAccordionTrigger>
                Third-party Providers
              </CatalogAccordionTrigger>
              <CatalogAccordionContent className="-mx-2 space-y-3 pb-5">
                {thirdPartyDrafts.map((draft) => {
                  const persisted = persistedById[draft.id] ?? null
                  return (
                    <ProviderCard
                      key={draft.id}
                      draft={draft}
                      persisted={persisted}
                      onFieldChange={(patch) => onProviderFieldChange(draft.id, patch)}
                      onGetModels={() => onGetProviderModels(draft.id)}
                      onEndpointTest={(modelId) => onTestProviderEndpoint(draft.id, modelId)}
                      onDelete={() => onDeleteProvider(draft.id)}
                      providerKind="third-party"
                      showManualModelPanel={shouldShowManualModelPanel(draft, persisted)}
                      notableProviderKey={notableProviderKeyForDraft(draft)}
                      onModelsUpdated={(models) => onProviderModelsUpdated(draft.id, models)}
                    />
                  )
                })}
                {thirdPartyDrafts.length === 0 ? (
                  <div className="flex flex-col items-center gap-3 rounded-md border border-dashed border-border/60 bg-muted/10 px-4 py-8 text-center">
                    <p className="text-xs text-muted-foreground">No third-party providers configured.</p>
                  </div>
                ) : null}
                <Button type="button" variant="default" onClick={() => void onAddProvider(createBlankAddProviderSubmission())} className="gap-1">
                  <Plus className="size-3.5" />
                  Add Provider
                </Button>
              </CatalogAccordionContent>
            </CatalogAccordionItem>
          </CatalogAccordion>
        )}
      </div>
    </div>
  )
}
