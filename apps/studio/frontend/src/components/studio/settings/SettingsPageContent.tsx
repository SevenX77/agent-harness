import { Bot, KeyRound, Plug, Settings, X } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ApiKeysTab } from "./api-keys/ApiKeysTab"
import { CopilotTab } from "./copilot/CopilotTab"
import { GeneralTab } from "./GeneralTab"
import { GeneralTabSkeleton } from "./GeneralTabSkeleton"
import { LlmRolesTab } from "./LlmRolesTab"
import { RolesTabSkeleton } from "./RolesTabSkeleton"
import { SettingsErrorBoundary } from "./SettingsErrorBoundary"
import { NavButton } from "./shared"
import type { SettingsPageContentProps } from "./types"

export function SettingsPageContent({
  activeTab,
  credentials,
  credentialsLoading,
  credentialsError,
  drafts,
  pendingAddProviderId,
  saveStatus,
  rolesData,
  modelGroups,
  rolesSaveStatus,
  rolesError,
  appSettings,
  onClose,
  onTabChange,
  onProviderFieldChange,
  onGetProviderModels,
  onDeleteProvider,
  onDeleteProviderEndpoints,
  onBeginAddProvider,
  onAddProvider,
  onCancelAddProvider,
  onProviderModelsUpdated,
  onRolesDataChange,
  onDeleteRole,
  onDeleteModelBundle,
  onBeforeRoleTest,
  onAfterRoleTest,
  onNavigateToApiKeys,
}: SettingsPageContentProps) {
  const { t } = useTranslation("settings")

  return (
    <div className="flex size-full flex-col bg-background">
      <div className="flex h-11 shrink-0 items-center justify-end border-b border-border px-2">
        <Button variant="ghost" size="icon" onClick={onClose} aria-label={t("shell.close")} className="size-7">
          <X className="size-4" />
        </Button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <nav className="flex w-full shrink-0 gap-1 overflow-x-auto border-b border-border bg-sidebar/40 px-2 py-2 md:w-56 md:flex-col md:border-b-0 md:border-r md:py-4">
          <NavButton active={activeTab === "general"} icon={<Settings />} onClick={() => onTabChange("general")}>
            {t("tabs.general")}
          </NavButton>
          <NavButton active={activeTab === "api_keys"} icon={<KeyRound />} onClick={() => onTabChange("api_keys")}>
            {t("tabs.apiKeys")}
          </NavButton>
          <NavButton active={activeTab === "llm_roles"} icon={<Plug />} onClick={() => onTabChange("llm_roles")}>
            {t("tabs.llmRoles")}
          </NavButton>
          <NavButton active={activeTab === "copilot"} icon={<Bot />} onClick={() => onTabChange("copilot")}>
            {t("tabs.copilot")}
          </NavButton>
        </nav>

        {activeTab === "llm_roles" ? (
          <div className="min-w-0 flex-1 overflow-y-auto lg:overflow-hidden">
            <div className="mx-auto flex min-h-full w-full max-w-6xl flex-col px-4 py-6 sm:px-6 md:px-8 md:py-8 lg:h-full lg:min-h-0">
              <SettingsErrorBoundary label="LLM Roles">
                {rolesData === null && !rolesError ? (
                  <RolesTabSkeleton />
                ) : (
                  <LlmRolesTab
                    data={rolesData}
                    credentials={credentials}
                    modelGroups={modelGroups}
                    saveStatus={rolesSaveStatus}
                    error={rolesError}
                    onChange={onRolesDataChange}
                    onDeleteRole={onDeleteRole}
                    onDeleteModelBundle={onDeleteModelBundle}
                    onBeforeRoleTest={onBeforeRoleTest}
                    onAfterRoleTest={onAfterRoleTest}
                    onNavigateToApiKeys={onNavigateToApiKeys}
                  />
                )}
              </SettingsErrorBoundary>
            </div>
          </div>
        ) : activeTab === "copilot" ? (
          <div className="min-w-0 flex-1 overflow-y-auto lg:overflow-hidden">
            <div className="mx-auto flex min-h-full w-full max-w-6xl flex-col px-4 py-6 sm:px-6 md:px-8 md:py-8 lg:h-full lg:min-h-0">
              <SettingsErrorBoundary label="Copilot">
                {rolesData === null && !rolesError ? (
                  <RolesTabSkeleton />
                ) : (
                  <CopilotTab
                    data={rolesData}
                    credentials={credentials}
                    modelGroups={modelGroups}
                    onChange={onRolesDataChange}
                    saveStatus={rolesSaveStatus}
                    error={rolesError}
                    // R-F3: route delete through the real DELETE endpoint (LlmRolesTab
                    // already uses it). Without this, the FE-only delete + PUT would
                    // be merged additively by the backend and never drop the yaml key.
                    onDeleteRole={onDeleteRole}
                    // R-F7: flush any debounced roles save before the SDK Test so the
                    // gateway snapshot is up to date and Test doesn't race the writer.
                    onBeforeRoleTest={onBeforeRoleTest}
                    // R-F12: empty-state + per-card warnings link to the API Keys tab.
                    onNavigateToApiKeys={onNavigateToApiKeys}
                  />
                )}
              </SettingsErrorBoundary>
            </div>
          </div>

        ) : (
          <ScrollArea className="flex-1">
            <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 md:px-8 md:py-8">
              {activeTab === "general" ? (
                <SettingsErrorBoundary label="General">
                  {appSettings.isLoading ? (
                    <GeneralTabSkeleton />
                  ) : (
                    <GeneralTab appSettings={appSettings} />
                  )}
                </SettingsErrorBoundary>
              ) : null}
              {activeTab === "api_keys" ? (
                <SettingsErrorBoundary label="API Keys">
                  <ApiKeysTab
                    credentials={credentials}
                    credentialsLoading={credentialsLoading}
                    credentialsError={credentialsError}
                    drafts={drafts}
                    pendingAddProviderId={pendingAddProviderId}
                    saveStatus={saveStatus}
                    onProviderFieldChange={onProviderFieldChange}
                    onGetProviderModels={onGetProviderModels}
                    onDeleteProvider={onDeleteProvider}
                    onDeleteProviderEndpoints={onDeleteProviderEndpoints}
                    onBeginAddProvider={onBeginAddProvider}
                    onAddProvider={onAddProvider}
                    onCancelAddProvider={onCancelAddProvider}
                    onProviderModelsUpdated={onProviderModelsUpdated}
                  />
                </SettingsErrorBoundary>
              ) : null}
            </div>
          </ScrollArea>
        )}
      </div>
    </div>
  )
}
