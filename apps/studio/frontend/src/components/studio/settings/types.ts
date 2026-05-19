import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import type { CredentialsState, ProviderType, RolesData } from "../../../api/llm"

export type SettingsTab = "general" | "api_keys" | "llm_roles"

export interface ProviderDraft {
  id: string
  name: string
  provider_type: ProviderType
  base_url: string
  api_key: string
  isTesting: boolean
}

export interface SettingsPageProps {
  onClose: () => void
}

export interface SettingsPageContentProps {
  activeTab: SettingsTab
  credentials: CredentialsState
  drafts: ProviderDraft[]
  saveStatus: SaveStatus
  rolesData: RolesData | null
  selectedRole: string
  rolesDirty: boolean
  rolesError: string | null
  appSettings: {
    userId: string
    giteaHost: string
    isLoading: boolean
    setUserId: (value: string) => void
    setGiteaHost: (value: string) => void
    save: () => void | Promise<unknown>
  }
  onClose: () => void
  onTabChange: (tab: SettingsTab) => void
  onProviderFieldChange: (providerId: string, patch: Partial<ProviderDraft>) => void
  onTestProvider: (providerId: string) => void
  onDeleteProvider: (providerId: string) => void
  onAddProvider: () => void
  onSelectedRoleChange: (roleName: string) => void
  onRolesDataChange: (next: RolesData) => void
  onSaveRoles: () => void
}
