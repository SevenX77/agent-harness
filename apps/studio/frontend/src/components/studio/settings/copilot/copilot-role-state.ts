import {
  isClaudeAgentSdkCompatibleRoute,
  type CopilotRolePreview,
} from "./mock-copilot-data"

export interface ActiveCopilotRoleCard {
  id: string
  title: string
  description: string
  source: CopilotRolePreview["source"]
  modelGroupId: string | null
}

export function createInitialCopilotRoles(
  roleIds: readonly string[],
  modelGroups: readonly CopilotRolePreview[],
): ActiveCopilotRoleCard[] {
  return roleIds.flatMap((roleId) => {
    const modelGroup = modelGroups.find((candidate) => candidate.id === roleId)
    if (!modelGroup) return []
    return [{
      id: roleId,
      title: modelGroup.title,
      description: modelGroup.description,
      source: modelGroup.source,
      modelGroupId: modelGroup.id,
    }]
  })
}

export function createDraftCopilotRole(index: number): ActiveCopilotRoleCard {
  return {
    id: `draft-copilot-role-${index}`,
    title: `New Copilot role ${index}`,
    description: "Select one model group for this Copilot role.",
    source: "third_party",
    modelGroupId: null,
  }
}

export function applyModelGroupToRole(
  roles: readonly ActiveCopilotRoleCard[],
  roleId: string,
  modelGroup: CopilotRolePreview,
): ActiveCopilotRoleCard[] {
  return roles.map((role) => {
    if (role.id !== roleId) return role
    return {
      ...role,
      title: modelGroup.title,
      description: modelGroup.description,
      modelGroupId: modelGroup.id,
    }
  })
}

export function availableCopilotModelGroups(
  modelGroups: readonly CopilotRolePreview[],
  roles: readonly ActiveCopilotRoleCard[],
): CopilotRolePreview[] {
  const selectedModelGroupIds = new Set(
    roles.map((role) => role.modelGroupId).filter(isModelGroupId),
  )
  return modelGroups.filter((modelGroup) => (
    !selectedModelGroupIds.has(modelGroup.id)
    && modelGroup.sdkId === "claude-agent-sdk"
    && modelGroup.availableRoutes.some(isClaudeAgentSdkCompatibleRoute)
  ))
}

export function copilotSwitchableRoles(
  roles: readonly ActiveCopilotRoleCard[],
): ActiveCopilotRoleCard[] {
  return roles.filter((role) => role.modelGroupId !== null)
}

function isModelGroupId(modelGroupId: string | null): modelGroupId is string {
  return typeof modelGroupId === "string"
}
