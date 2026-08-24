import { useMemo } from "react"
import { Plus, TriangleAlert } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  CatalogAccordion,
  CatalogAccordionContent,
  CatalogAccordionItem,
  CatalogAccordionTrigger,
} from "@/components/ui/catalog-accordion"
import { SaveStatusBadge } from "@/components/ui/save-status-badge"
import type { CommunitySharingChoice } from "@/api/types"
import { AddProviderForm, ProviderCard, ProviderListSkeleton } from "../../api-keys"
import { officialProviderDrafts, thirdPartyProviderDrafts, notableProviderKeyForDraft, providerEndpointDraftsForAction, shouldShowManualModelPanel } from "../provider-utils"
import { SectionTitle } from "../shared"
import type { SettingsPageContentProps } from "../types"

export function ApiKeysTab({
  credentials,
  credentialsLoading,
  credentialsError,
  drafts,
  pendingAddProviderId,
  saveStatus,
  backendReachable,
  communitySharingChoice,
  onProviderFieldChange,
  onRevealProviderSecret,
  onGetProviderModels,
  onProbeEndpoint,
  onForceEndpointTest,
  onDeleteProvider,
  onDeleteProviderEndpoints,
  onRemoveModel,
  onBeginAddProvider,
  onAddProvider,
  onCancelAddProvider,
  onProviderModelsUpdated,
}: Pick<
  SettingsPageContentProps,
  | "credentials"
  | "credentialsLoading"
  | "credentialsError"
  | "drafts"
  | "pendingAddProviderId"
  | "saveStatus"
  | "backendReachable"
  | "onProviderFieldChange"
  | "onRevealProviderSecret"
  | "onGetProviderModels"
  | "onProbeEndpoint"
  | "onForceEndpointTest"
  | "onDeleteProvider"
  | "onDeleteProviderEndpoints"
  | "onRemoveModel"
  | "onBeginAddProvider"
  | "onAddProvider"
  | "onCancelAddProvider"
  | "onProviderModelsUpdated"
> & {
  /** SSOT: the community-sharing state lives only in `AppSettings.community_sharing_choice`
   * (`SettingsPageContentProps["appSettings"]["communitySharingChoice"]`); passed down as its
   * own prop rather than re-derived from the registry response, which carries no such field. */
  communitySharingChoice: CommunitySharingChoice
}) {
  const { t } = useTranslation("settings")
  const persistedById = useMemo(
    () => Object.fromEntries(credentials.providers.map((provider) => [provider.id, provider])),
    [credentials.providers],
  )
  const officialDrafts = useMemo(() => officialProviderDrafts(drafts), [drafts])
  const thirdPartyDrafts = useMemo(() => thirdPartyProviderDrafts(drafts), [drafts])
  const pendingAddProviderActive = Boolean(
    pendingAddProviderId && thirdPartyDrafts.some((draft) => draft.id === pendingAddProviderId),
  )

  return (
    <div className="max-w-3xl">
      <SectionTitle
        title={t("apiKeys.title")}
        description={t("apiKeys.description")}
        trailing={<SaveStatusBadge status={saveStatus} />}
      />
      <ProbeCatalogStatus probeCatalog={credentials.probe_catalog} communitySharingChoice={communitySharingChoice} />
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
              <CatalogAccordionContent className="space-y-3 pb-5">
                {officialDrafts.map((draft) => {
                  const endpointDrafts = providerEndpointDraftsForAction(draft)
                  const persistedEndpoints = Object.fromEntries(
                    endpointDrafts.map((endpointDraft) => [
                      endpointDraft.id,
                      persistedById[endpointDraft.id] ?? null,
                    ]),
                  )
                  const persisted = persistedById[draft.id]
                    ?? endpointDrafts.map((endpointDraft) => persistedById[endpointDraft.id]).find(Boolean)
                    ?? null
                  return (
                    <ProviderCard
                      key={draft.id}
                      draft={draft}
                      persisted={persisted}
                      persistedEndpoints={persistedEndpoints}
                      onFieldChange={(patch, options) => onProviderFieldChange(draft.id, { ...draft, ...patch }, options)}
                      onRevealApiKey={() => onRevealProviderSecret(draft.id)}
                      onGetModels={() => onGetProviderModels(draft.id)}
                      onProbeEndpoint={onProbeEndpoint}
                      onForceEndpointTest={onForceEndpointTest}
                      onDelete={() => onDeleteProvider(draft.id)}
                      onDeleteEndpointIds={onDeleteProviderEndpoints}
                      onRemoveModel={onRemoveModel}
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
              <CatalogAccordionContent className="space-y-3 pb-5">
                {thirdPartyDrafts.map((draft) => {
                  if (draft.id === pendingAddProviderId) {
                    return (
                      <AddProviderForm
                        key={draft.id}
                        existingNames={thirdPartyDrafts
                          .filter((item) => item.id !== pendingAddProviderId)
                          .map((item) => item.name)}
                        onSubmit={onAddProvider}
                        onCancel={onCancelAddProvider}
                      />
                    )
                  }
                  const persisted = persistedById[draft.id] ?? null
                  const persistedEndpoints = Object.fromEntries(
                    providerEndpointDraftsForAction(draft).map((endpointDraft) => [
                      endpointDraft.id,
                      persistedById[endpointDraft.id]
                        ?? credentials.providers.find((provider) => (
                          provider.provider_type === endpointDraft.provider_type &&
                          normalizeBaseUrl(provider.base_url) === normalizeBaseUrl(endpointDraft.base_url)
                        ))
                        ?? null,
                    ]),
                  )
                  return (
                    <ProviderCard
                      key={draft.id}
                      draft={draft}
                      persisted={persisted}
                      persistedEndpoints={persistedEndpoints}
                      onFieldChange={(patch, options) => onProviderFieldChange(draft.id, patch, options)}
                      onRevealApiKey={() => onRevealProviderSecret(draft.id)}
                      onGetModels={() => onGetProviderModels(draft.id)}
                      onProbeEndpoint={onProbeEndpoint}
                      onForceEndpointTest={onForceEndpointTest}
                      onDelete={() => onDeleteProvider(draft.id)}
                      onDeleteEndpointIds={onDeleteProviderEndpoints}
                      onRemoveModel={onRemoveModel}
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
                {pendingAddProviderActive ? null : (
                  <Button
                    type="button"
                    variant="default"
                    onClick={onBeginAddProvider}
                    className="gap-1"
                    disabled={backendReachable === false}
                    title={backendReachable === false ? t("apiKeys.backendReconnecting") : undefined}
                  >
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

function normalizeBaseUrl(value?: string | null): string {
  return (value ?? "").trim().replace(/\/+$/, "").toLowerCase()
}

/**
 * Sharing badge + message text for the three `community_sharing_choice` states.
 * This is a plain, non-consent-facing status line (unlike the first-run consent
 * dialog copy, which is fixed word-for-word) — it just has to stay truthful to
 * what the backend will actually do, which is exactly what used to drift here
 * (a hardcoded "Local only" while the toggle defaulted to sharing).
 */
function sharingStatusCopy(choice: CommunitySharingChoice): { badge: string; message: string } {
  switch (choice) {
    case "shared":
      return {
        badge: "Sharing with community",
        message: "Probe-verified evidence is shared with the community catalog. Turn off in Settings → General.",
      }
    case "declined":
      return {
        badge: "Local only",
        message: "Community sharing is off — probes stay local. Turn on in Settings → General.",
      }
    case "unset":
      return {
        badge: "Local only",
        message: "Not sharing yet. Turn on community sharing in Settings → General.",
      }
  }
}

function ProbeCatalogStatus({
  probeCatalog,
  communitySharingChoice,
}: {
  probeCatalog: SettingsPageContentProps["credentials"]["probe_catalog"]
  communitySharingChoice: CommunitySharingChoice
}) {
  if (!probeCatalog) return null
  const community = probeCatalog.community_catalog
  const remoteSynced = Boolean(community?.synced)
  const sharing = sharingStatusCopy(communitySharingChoice)
  return (
    <div
      className="mb-4 space-y-2 rounded-md border border-border/60 bg-muted/10 px-3 py-2 text-xs text-muted-foreground"
      data-testid="probe-catalog-status"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-foreground">Local probe evidence</span>
        <Badge variant="success">{probeCatalog.local_verified_records_count} verified</Badge>
        <Badge variant={probeCatalog.local_failed_records_count > 0 ? "warning" : "secondary"}>
          {probeCatalog.local_failed_records_count} failed
        </Badge>
        <Badge variant="outline">
          {remoteSynced ? "Remote catalog synced" : "Remote catalog not synced"}
        </Badge>
        {community && community.record_count > 0 ? (
          <Badge variant="secondary">{community.record_count} community-verified</Badge>
        ) : null}
        <Badge variant={communitySharingChoice === "shared" ? "success" : "secondary"}>{sharing.badge}</Badge>
        <span className="min-w-0">{sharing.message}</span>
      </div>
    </div>
  )
}
