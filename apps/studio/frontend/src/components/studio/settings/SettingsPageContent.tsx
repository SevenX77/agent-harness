import type { ReactNode } from "react"
import { KeyRound, Plug, Settings, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import { ApiKeysTab } from "./api-keys/ApiKeysTab"
import { GeneralTab } from "./GeneralTab"
import { LlmRolesTab } from "./LlmRolesTab"
import type { SettingsPageContentProps } from "./types"

export function SettingsPageContent({
  activeTab,
  credentials,
  drafts,
  saveStatus,
  rolesData,
  selectedRole,
  rolesDirty,
  rolesError,
  appSettings,
  onClose,
  onTabChange,
  onProviderFieldChange,
  onTestProvider,
  onDeleteProvider,
  onAddProvider,
  onSelectedRoleChange,
  onRolesDataChange,
  onSaveRoles,
}: SettingsPageContentProps) {
  return (
    <div className="flex size-full flex-col bg-background">
      <div className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-border pl-4 pr-2">
        <span className="text-sm font-semibold text-foreground">Settings</span>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close settings" className="size-7">
          <X className="size-4" />
        </Button>
      </div>

      <div className="flex min-h-0 flex-1">
        <nav className="w-56 shrink-0 border-r border-border bg-sidebar/40 px-2 py-4">
          <NavButton active={activeTab === "general"} icon={<Settings />} onClick={() => onTabChange("general")}>
            General
          </NavButton>
          <NavButton active={activeTab === "api_keys"} icon={<KeyRound />} onClick={() => onTabChange("api_keys")}>
            API Keys
          </NavButton>
          <NavButton active={activeTab === "llm_roles"} icon={<Plug />} onClick={() => onTabChange("llm_roles")}>
            LLM Roles
          </NavButton>
        </nav>

        <ScrollArea className="flex-1">
          <div className="max-w-3xl px-10 py-8">
            {activeTab === "general" ? <GeneralTab appSettings={appSettings} /> : null}
            {activeTab === "api_keys" ? (
              <ApiKeysTab
                credentials={credentials}
                drafts={drafts}
                saveStatus={saveStatus}
                onProviderFieldChange={onProviderFieldChange}
                onTestProvider={onTestProvider}
                onDeleteProvider={onDeleteProvider}
                onAddProvider={onAddProvider}
              />
            ) : null}
            {activeTab === "llm_roles" ? (
              <LlmRolesTab
                data={rolesData}
                credentials={credentials}
                selectedRole={selectedRole}
                dirty={rolesDirty}
                error={rolesError}
                onSelectedRoleChange={onSelectedRoleChange}
                onChange={onRolesDataChange}
                onSave={onSaveRoles}
              />
            ) : null}
          </div>
        </ScrollArea>
      </div>
    </div>
  )
}

function NavButton({
  active,
  icon,
  children,
  onClick,
}: {
  active: boolean
  icon: ReactNode
  children: ReactNode
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-sm px-2.5 py-1.5 text-xs transition-colors [&_svg]:size-3.5",
        active ? "bg-sidebar-accent text-foreground" : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
      )}
    >
      {icon}
      {children}
    </button>
  )
}
