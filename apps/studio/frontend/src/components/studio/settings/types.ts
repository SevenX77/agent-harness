import type { ReactNode } from "react"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import type { CredentialsState, ModelGroup, ModelInfo, ProviderType, RolesData } from "../../../api/llm"
import type { AddProviderFormSubmission } from "../api-keys"

export type SettingsTab = "general" | "api_keys" | "llm_roles" | "copilot"

export interface ProviderDraft {
  id: string
  name: string
  provider_type: ProviderType
  base_url: string
  api_key: string
  isTesting: boolean
  testingAction?: "models" | "endpoint" | null
}

export interface SettingsPageProps {
  onClose: () => void
}

export interface SettingsPageContentProps {
  activeTab: SettingsTab
  credentials: CredentialsState
  credentialsLoading: boolean
  credentialsError: string | null
  drafts: ProviderDraft[]
  saveStatus: SaveStatus
  rolesData: RolesData | null
  modelGroups: ModelGroup[]
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
  /**
   * N0 Settings · Shell (atoms #5/#6): true only after the /ws/events stream's
   * reconnect backoff has consistently failed past the flicker threshold. The
   * top bar shows a "connection lost" warning to the right of the save badge.
   */
  connectionLost?: boolean
  onClose: () => void
  onTabChange: (tab: SettingsTab) => void
  onProviderFieldChange: (providerId: string, patch: Partial<ProviderDraft>) => void
  onGetProviderModels: (providerId: string) => void
  onTestProviderEndpoint: (providerId: string, modelId: string) => void
  onDeleteProvider: (providerId: string) => void
  onAddProvider: (data: AddProviderFormSubmission) => Promise<void> | void
  onProviderModelsUpdated: (providerId: string, models: ModelInfo[]) => void
  onRolesDataChange: (next: RolesData) => void
  onDeleteRole: (roleName: string) => void
  onDeleteModelBundle: (bundleId: string) => void
  onBeforeRoleTest: () => Promise<RolesData | null>
  onAfterRoleTest: () => Promise<void> | void
  /**
   * #35 (spec §2.1): a failed provider row with reason_code === "missing_config"
   * offers a "Configure" affordance that jumps to the API Keys tab. SettingsPage
   * owns the active tab, so the callback flows down through here to the sidebar.
   */
  onNavigateToApiKeys: () => void
}

export type { ReactNode }
