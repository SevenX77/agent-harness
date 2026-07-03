import type { ReactNode } from "react"
import type { AppLanguage } from "@/api/types"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import type { CredentialsState, ModelGroup, ModelInfo, ProviderType, RolesData } from "../../../api/llm"
import type { AddProviderFormSubmission } from "../api-keys"

export type SettingsTab = "general" | "api_keys" | "llm_roles" | "copilot"

export interface ProviderDraft {
  id: string
  name: string
  provider_type: ProviderType
  base_url: string
  base_urls?: Array<{
    id: string
    value: string
    provider_type?: ProviderType
    endpoint_ids?: Partial<Record<ProviderType, string>>
  }>
  api_key: string
  isTesting: boolean
  testingAction?: "models" | null
}

export interface ProviderDraftChangeOptions {
  save?: boolean
}

export interface SettingsPageProps {
  onClose: () => void
  initialTab?: SettingsTab
}

export interface SettingsPageController extends Omit<
  SettingsPageContentProps,
  "activeTab" | "onClose" | "onTabChange" | "onNavigateToApiKeys"
> {
  ensureCredentialsHydrated: () => void
}

export interface SettingsPageViewProps extends SettingsPageProps {
  controller: SettingsPageController
}

export interface SettingsPageContentProps {
  activeTab: SettingsTab
  credentials: CredentialsState
  credentialsLoading: boolean
  credentialsError: string | null
  drafts: ProviderDraft[]
  pendingAddProviderId: string | null
  saveStatus: SaveStatus
  rolesData: RolesData | null
  modelGroups: ModelGroup[]
  rolesSaveStatus: SaveStatus
  rolesError: string | null
  appSettings: {
    userId: string
    giteaHost: string
    defaultSkillsDirectory: string
    language: AppLanguage
    remoteModelCatalogEnabled: boolean
    isLoading: boolean
    saveStatus: SaveStatus
    setUserId: (value: string) => void
    setGiteaHost: (value: string) => void
    setDefaultSkillsDirectory: (value: string) => void
    setLanguage: (value: AppLanguage) => void
    setRemoteModelCatalogEnabled: (value: boolean) => void
  }
  /**
   * N0 Settings · Shell (atoms #5/#6): true only after the /ws/events stream's
   * reconnect backoff has consistently failed past the flicker threshold. The
   * top bar shows a "connection lost" warning to the right of the save badge.
   */
  connectionLost?: boolean
  /**
   * Live backend reachability = API config resolved AND the event stream is
   * connected. Mutating settings actions (delete / test / add) are gated on
   * this: when false they are refused with a "reconnecting" message and the UI
   * disables the buttons, so nothing fires into an unreachable backend.
   * Undefined is treated as reachable (test fixtures / non-gated surfaces).
   */
  backendReachable?: boolean
  onClose: () => void
  onTabChange: (tab: SettingsTab) => void
  onProviderFieldChange: (providerId: string, patch: Partial<ProviderDraft>, options?: ProviderDraftChangeOptions) => void
  onGetProviderModels: (providerId: string) => void
  /** Force re-probe one (URL, protocol) cell, bypassing the half-life gate (design §1.2 matrix point 4). */
  onForceEndpointTest: (endpointId: string) => void
  onDeleteProvider: (providerId: string) => void
  onDeleteProviderEndpoints: (endpointIds: string[]) => void
  onBeginAddProvider: () => void
  onAddProvider: (data: AddProviderFormSubmission) => Promise<void> | void
  onCancelAddProvider: () => void
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
