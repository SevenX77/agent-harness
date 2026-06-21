import { useMemo, useState } from "react"
import { Plus, TriangleAlert } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  CatalogAccordion,
  CatalogAccordionContent,
  CatalogAccordionItem,
  CatalogAccordionTrigger,
} from "@/components/ui/catalog-accordion"
import { SaveStatusBadge } from "@/components/ui/save-status-badge"
import { AddProviderForm, ProviderCard, ProviderListSkeleton } from "../../api-keys"
import { officialProviderDrafts, thirdPartyProviderDrafts, notableProviderKeyForDraft, shouldShowManualModelPanel } from "../provider-utils"
import { SectionTitle } from "../shared"
import type { SettingsPageContentProps } from "../types"

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
  const { t } = useTranslation("settings")
  const [addProviderOpen, setAddProviderOpen] = useState(false)
  const persistedById = useMemo(
    () => Object.fromEntries(credentials.providers.map((provider) => [provider.id, provider])),
    [credentials.providers],
  )
  const officialDrafts = useMemo(() => officialProviderDrafts(drafts), [drafts])
  const thirdPartyDrafts = useMemo(() => thirdPartyProviderDrafts(drafts), [drafts])

  return (
    <div className="max-w-3xl">
      <SectionTitle
        title={t("apiKeys.title")}
        description={t("apiKeys.description")}
        trailing={<SaveStatusBadge status={saveStatus} />}
      />
      <div className="space-y-4" data-testid="api-keys-list">
        {credentialsLoading ? (
          <ProviderListSkeleton count={5} />
        ) : credentialsError ? (
          <Alert variant="destructive">
            <TriangleAlert className="size-3.5" />
            <AlertTitle>{t("apiKeys.loadFailedTitle")}</AlertTitle>
            <AlertDescription>
              {t("apiKeys.loadFailedDescription", { error: credentialsError })}
            </AlertDescription>
          </Alert>
        ) : (
          <CatalogAccordion
            type="multiple"
            defaultValue={["official", "third-party"]}
          >
            <CatalogAccordionItem value="official">
              <CatalogAccordionTrigger>
                {t("apiKeys.officialProviders")}
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
                {t("apiKeys.thirdPartyProviders")}
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
                    <p className="text-xs text-muted-foreground">{t("apiKeys.noThirdPartyProviders")}</p>
                  </div>
                ) : null}
                {addProviderOpen ? (
                  <AddProviderForm
                    existingNames={thirdPartyDrafts.map((d) => d.name)}
                    onSubmit={(submission) => {
                      onAddProvider(submission)
                      setAddProviderOpen(false)
                    }}
                    onCancel={() => setAddProviderOpen(false)}
                  />
                ) : (
                  <Button type="button" variant="default" onClick={() => setAddProviderOpen(true)} className="gap-1">
                    <Plus className="size-3.5" />
                    {t("apiKeys.addProvider")}
                  </Button>
                )}
              </CatalogAccordionContent>
            </CatalogAccordionItem>
          </CatalogAccordion>
        )}
      </div>
    </div>
  )
}
