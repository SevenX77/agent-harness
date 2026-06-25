import { Bot, KeyRound, Plug, Settings, WifiOff, X } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { SaveStatusBadge } from "@/components/ui/save-status-badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ApiKeysTab } from "./api-keys/ApiKeysTab"
import { CopilotTab } from "./copilot/CopilotTab"
import { GeneralTab } from "./GeneralTab"
import { GeneralTabSkeleton } from "./GeneralTabSkeleton"
import { LlmRolesTab } from "./LlmRolesTab"
import { RolesTabSkeleton } from "./RolesTabSkeleton"
import { SettingsErrorBoundary } from "./SettingsErrorBoundary"
import { mergeSaveStatuses } from "./save-status-merge"
import { NavButton } from "./shared"
import type { SettingsPageContentProps } from "./types"

export function SettingsPageContent({
  activeTab,
  credentials,
  credentialsLoading,
  credentialsError,
  drafts,
  saveStatus,
  rolesData,
  modelGroups,
  rolesSaveStatus,
  rolesError,
  appSettings,
  connectionLost = false,
  onClose,
  onTabChange,
  onProviderFieldChange,
  onGetProviderModels,
  onDeleteProvider,
  onAddProvider,
  onProviderModelsUpdated,
  onRolesDataChange,
  onDeleteRole,
  onDeleteModelBundle,
  onBeforeRoleTest,
  onAfterRoleTest,
  onNavigateToApiKeys,
}: SettingsPageContentProps) {
  const { t } = useTranslation("settings")

  const globalSaveStatus = mergeSaveStatuses([saveStatus, rolesSaveStatus, appSettings.saveStatus])

  return (
    <div className="flex size-full flex-col bg-background">
      <div className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-border pl-4 pr-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="text-sm font-semibold text-foreground">{t("shell.title")}</span>
          <span data-shell-save-status={globalSaveStatus}>
            <SaveStatusBadge status={globalSaveStatus} />
          </span>
          {connectionLost ? (
            <Badge
              variant="warning"
              className="gap-1 text-[10px] font-normal"
              data-shell-connection-lost="true"
              aria-live="assertive"
            >
              <WifiOff className="size-3" aria-hidden="true" />
              {t("shell.connectionLost")}
            </Badge>
          ) : null}
        </div>
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
          <ScrollArea className="flex-1">
            <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 md:px-8 md:py-8">
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
          </ScrollArea>

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
                    saveStatus={saveStatus}
                    onProviderFieldChange={onProviderFieldChange}
                    onGetProviderModels={onGetProviderModels}
                    onDeleteProvider={onDeleteProvider}
                    onAddProvider={onAddProvider}
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
