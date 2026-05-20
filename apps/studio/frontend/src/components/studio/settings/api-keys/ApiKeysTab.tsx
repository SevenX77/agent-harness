import { useMemo, useState } from "react"
import { Check, Loader2, Plus, TriangleAlert } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import { AddProviderForm, ProviderCard, ProviderListSkeleton } from "../../api-keys"
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
  drafts,
  saveStatus,
  onProviderFieldChange,
  onTestProvider,
  onDeleteProvider,
  onAddProvider,
  onProviderModelsUpdated,
}: Pick<
  SettingsPageContentProps,
  | "credentials"
  | "credentialsLoading"
  | "drafts"
  | "saveStatus"
  | "onProviderFieldChange"
  | "onTestProvider"
  | "onDeleteProvider"
  | "onAddProvider"
  | "onProviderModelsUpdated"
>) {
  const [showAddForm, setShowAddForm] = useState(false)
  const persistedById = useMemo(
    () => Object.fromEntries(credentials.providers.map((provider) => [provider.id, provider])),
    [credentials.providers],
  )
  const officialDrafts = useMemo(() => officialProviderDrafts(drafts), [drafts])
  const thirdPartyDrafts = useMemo(() => thirdPartyProviderDrafts(drafts), [drafts])

  return (
    <div>
      <SectionTitle
        title="API Keys"
        description="Local LLM provider credentials used by Studio runtime. Changes auto-save."
        trailing={<SaveStatusBadge status={saveStatus} />}
      />
      <div className="space-y-4" data-testid="api-keys-list">
        {credentialsLoading ? (
          <ProviderListSkeleton count={5} />
        ) : (
          <>
            <section className="space-y-3" aria-label="Official Providers">
              <h3 className="text-sm font-medium text-foreground">Official Providers</h3>
              {officialDrafts.map((draft) => {
                const persisted = persistedById[draft.id] ?? null
                return (
                  <ProviderCard
                    key={draft.id}
                    draft={draft}
                    persisted={persisted}
                    onFieldChange={(patch) => onProviderFieldChange(draft.id, { ...draft, ...patch })}
                    onTest={() => onTestProvider(draft.id)}
                    onDelete={() => onDeleteProvider(draft.id)}
                    providerKind="official"
                    showManualModelPanel={shouldShowManualModelPanel(draft, persisted)}
                    notableProviderKey={notableProviderKeyForDraft(draft)}
                    onModelsUpdated={(models) => onProviderModelsUpdated(draft.id, models)}
                  />
                )
              })}
            </section>

            <section className="space-y-3 pt-4" aria-label="Third-party Providers">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-medium text-foreground">Third-party Providers</h3>
                {!showAddForm ? (
                  <Button type="button" variant="outline" onClick={() => setShowAddForm(true)} className="gap-1">
                    <Plus className="size-3.5" />
                    Add Provider
                  </Button>
                ) : null}
              </div>
              {thirdPartyDrafts.length > 0 ? (
                thirdPartyDrafts.map((draft) => {
                  const persisted = persistedById[draft.id] ?? null
                  return (
                    <ProviderCard
                      key={draft.id}
                      draft={draft}
                      persisted={persisted}
                      onFieldChange={(patch) => onProviderFieldChange(draft.id, patch)}
                      onTest={() => onTestProvider(draft.id)}
                      onDelete={() => onDeleteProvider(draft.id)}
                      providerKind="third-party"
                      showManualModelPanel={shouldShowManualModelPanel(draft, persisted)}
                      notableProviderKey={notableProviderKeyForDraft(draft)}
                      onModelsUpdated={(models) => onProviderModelsUpdated(draft.id, models)}
                    />
                  )
                })
              ) : !showAddForm ? (
                <div className="flex flex-col items-center gap-3 rounded-md border border-dashed border-border/60 bg-muted/10 px-4 py-8 text-center">
                  <p className="text-xs text-muted-foreground">No third-party providers configured.</p>
                </div>
              ) : null}
              {showAddForm ? (
                <AddProviderForm
                  onSubmit={async (data) => {
                    await onAddProvider(data)
                    setShowAddForm(false)
                  }}
                  onCancel={() => setShowAddForm(false)}
                />
              ) : null}
            </section>
          </>
        )}
      </div>
    </div>
  )
}
