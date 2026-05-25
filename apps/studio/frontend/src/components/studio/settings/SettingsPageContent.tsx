import { Plug, Router, Settings, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { EndpointsTab } from "./endpoints/EndpointsTab"
import { GeneralTab } from "./GeneralTab"
import { LlmRolesTab } from "./LlmRolesTab"
import { SettingsErrorBoundary } from "./SettingsErrorBoundary"
import { NavButton } from "./shared"
import type { SettingsPageContentProps } from "./types"

export function SettingsPageContent({
  activeTab,
  registry,
  registryLoading,
  registryError,
  endpointSaveStatus,
  importDrafts,
  rolesData,
  rolesSaveStatus,
  rolesError,
  appSettings,
  onClose,
  onTabChange,
  onAddEndpoint,
  onEndpointChange,
  onDeleteEndpoint,
  onTestEndpoint,
  onProbeRoute,
  onApplyDraft,
  onRolesDataChange,
  onProbeRole,
  onApplyProfile,
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
          <NavButton active={activeTab === "endpoints"} icon={<Router />} onClick={() => onTabChange("endpoints")}>
            Endpoints
          </NavButton>
          <NavButton active={activeTab === "llm_roles"} icon={<Plug />} onClick={() => onTabChange("llm_roles")}>
            LLM Roles
          </NavButton>
        </nav>

        {activeTab === "llm_roles" ? (
          <div className="min-w-0 flex-1 overflow-y-auto lg:overflow-hidden">
            <div className="mx-auto flex min-h-full w-full max-w-6xl flex-col px-4 py-6 sm:px-6 md:px-8 md:py-8 lg:h-full lg:min-h-0">
              <SettingsErrorBoundary label="LLM Roles">
                <LlmRolesTab
                  data={rolesData}
                  registry={registry}
                  saveStatus={rolesSaveStatus}
                  error={rolesError}
                  onChange={onRolesDataChange}
                  onProbeRole={onProbeRole}
                  onApplyProfile={onApplyProfile}
                />
              </SettingsErrorBoundary>
            </div>
          </div>
        ) : (
          <ScrollArea className="flex-1">
            <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 md:px-8 md:py-8">
              {activeTab === "general" ? <GeneralTab appSettings={appSettings} /> : null}
              {activeTab === "endpoints" ? (
                <EndpointsTab
                  registry={registry}
                  loading={registryLoading}
                  error={registryError}
                  saveStatus={endpointSaveStatus}
                  importDrafts={importDrafts}
                  onAddEndpoint={onAddEndpoint}
                  onEndpointChange={onEndpointChange}
                  onDeleteEndpoint={onDeleteEndpoint}
                  onTestEndpoint={onTestEndpoint}
                  onProbeRoute={onProbeRoute}
                  onApplyDraft={onApplyDraft}
                />
              ) : null}
            </div>
          </ScrollArea>
        )}
      </div>
    </div>
  )
}
