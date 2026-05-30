import { Bot, KeyRound, Plug, Settings, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ApiKeysTab } from "./api-keys/ApiKeysTab"
import { CopilotTab } from "./copilot/CopilotTab"
import { GeneralTab } from "./GeneralTab"
import { LlmRolesTab } from "./LlmRolesTab"
import { SettingsErrorBoundary } from "./SettingsErrorBoundary"
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
  onClose,
  onTabChange,
  onProviderFieldChange,
  onGetProviderModels,
  onTestProviderEndpoint,
  onDeleteProvider,
  onAddProvider,
  onProviderModelsUpdated,
  onRolesDataChange,
  onDeleteRole,
  onDeleteModelBundle,
  onBeforeRoleTest,
}: SettingsPageContentProps) {
  return (
    <div className="flex size-full flex-col bg-background">
      <div className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-border pl-4 pr-2">
        <span className="text-sm font-semibold text-foreground">Settings</span>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close settings" className="size-7">
          <X className="size-4" />
        </Button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <nav className="flex w-full shrink-0 gap-1 overflow-x-auto border-b border-border bg-sidebar/40 px-2 py-2 md:w-56 md:flex-col md:border-b-0 md:border-r md:py-4">
          <NavButton active={activeTab === "general"} icon={<Settings />} onClick={() => onTabChange("general")}>
            General
          </NavButton>
          <NavButton active={activeTab === "api_keys"} icon={<KeyRound />} onClick={() => onTabChange("api_keys")}>
            API Keys
          </NavButton>
          <NavButton active={activeTab === "llm_roles"} icon={<Plug />} onClick={() => onTabChange("llm_roles")}>
            LLM Roles
          </NavButton>
          <NavButton active={activeTab === "copilot"} icon={<Bot />} onClick={() => onTabChange("copilot")}>
            Copilot
          </NavButton>
        </nav>

        {activeTab === "llm_roles" ? (
          <div className="min-w-0 flex-1 overflow-y-auto lg:overflow-hidden">
            <div className="mx-auto flex min-h-full w-full max-w-6xl flex-col px-4 py-6 sm:px-6 md:px-8 md:py-8 lg:h-full lg:min-h-0">
              <SettingsErrorBoundary label="LLM Roles">
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
                />
              </SettingsErrorBoundary>
            </div>
          </div>
        ) : activeTab === "copilot" ? (
          <ScrollArea className="flex-1">
            <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 md:px-8 md:py-8">
              <SettingsErrorBoundary label="Copilot">
                <CopilotTab />
              </SettingsErrorBoundary>
            </div>
          </ScrollArea>
        ) : (
          <ScrollArea className="flex-1">
            <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 md:px-8 md:py-8">
              {activeTab === "general" ? <GeneralTab appSettings={appSettings} /> : null}
              {activeTab === "api_keys" ? (
                <ApiKeysTab
                  credentials={credentials}
                  credentialsLoading={credentialsLoading}
                  credentialsError={credentialsError}
                  drafts={drafts}
                  saveStatus={saveStatus}
                  onProviderFieldChange={onProviderFieldChange}
                  onGetProviderModels={onGetProviderModels}
                  onTestProviderEndpoint={onTestProviderEndpoint}
                  onDeleteProvider={onDeleteProvider}
                  onAddProvider={onAddProvider}
                  onProviderModelsUpdated={onProviderModelsUpdated}
                />
              ) : null}
            </div>
          </ScrollArea>
        )}
      </div>
    </div>
  )
}
