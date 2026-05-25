import type { ReactNode } from "react"
import type {
  ProviderEndpoint,
  ProviderImportDraft,
  RegistryResponse,
  RolesData,
} from "@/api/llm"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"

export type SettingsTab = "general" | "endpoints" | "llm_roles"

export interface SettingsPageProps {
  onClose: () => void
}

export interface SettingsPageContentProps {
  activeTab: SettingsTab
  registry: RegistryResponse | null
  registryLoading: boolean
  registryError: string | null
  endpointSaveStatus: SaveStatus
  importDrafts: ProviderImportDraft[]
  rolesData: RolesData | null
  rolesSaveStatus: SaveStatus
  rolesError: string | null
  appSettings: {
    userId: string
    giteaHost: string
    defaultSkillsDirectory: string
    isLoading: boolean
    saveStatus: SaveStatus
    setUserId: (value: string) => void
    setGiteaHost: (value: string) => void
    setDefaultSkillsDirectory: (value: string) => void
  }
  onClose: () => void
  onTabChange: (tab: SettingsTab) => void
  onAddEndpoint: () => void
  onEndpointChange: (endpointId: string, patch: Partial<ProviderEndpoint>) => void
  onDeleteEndpoint: (endpointId: string) => void
  onTestEndpoint: (endpointId: string) => void
  onProbeRoute: (routeId: string) => void
  onApplyDraft: (draftId: string) => void
  onRolesDataChange: (next: RolesData) => void
  onProbeRole: (roleName: string) => void
  onApplyProfile: (roleName: string, profileId: string) => void
}

export type { ReactNode }
