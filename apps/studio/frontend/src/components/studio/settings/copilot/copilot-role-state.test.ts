import { describe, expect, it } from "vitest"
import {
  applyModelGroupToRole,
  availableCopilotModelGroups,
  copilotSwitchableRoles,
  createDraftCopilotRole,
  createInitialCopilotRoles,
} from "./copilot-role-state"
import { mockCopilotRoles } from "./mock-copilot-data"

describe("copilot role state", () => {
  it("creates visible copilot role cards before a model group is selected", () => {
    const draft = createDraftCopilotRole(2)

    expect(draft).toEqual({
      id: "draft-copilot-role-2",
      title: "New Copilot role 2",
      description: "Select one model group for this Copilot role.",
      source: "third_party",
      modelGroupId: null,
    })
  })

  it("keeps the switchable copilot models equal to active copilot roles", () => {
    const roles = createInitialCopilotRoles(["copilot_opus_4_7", "copilot_deepseek_v4"], mockCopilotRoles)

    expect(copilotSwitchableRoles(roles).map((role) => role.id)).toEqual([
      "copilot_opus_4_7",
      "copilot_deepseek_v4",
    ])
  })

  it("lets a new role choose exactly one unselected compatible model group", () => {
    const roles = [
      ...createInitialCopilotRoles(["copilot_opus_4_7", "copilot_deepseek_v4"], mockCopilotRoles),
      createDraftCopilotRole(1),
    ]

    expect(availableCopilotModelGroups(mockCopilotRoles, roles).map((group) => group.id)).toEqual([
      "sonnet-4-7-third-party",
    ])

    const selected = mockCopilotRoles.find((group) => group.id === "sonnet-4-7-third-party")
    expect(selected).toBeDefined()
    const nextRoles = applyModelGroupToRole(roles, "draft-copilot-role-1", selected!)

    expect(nextRoles.at(-1)).toMatchObject({
      id: "draft-copilot-role-1",
      title: "Claude Sonnet 4.7 Copilot",
      source: "third_party",
      modelGroupId: "sonnet-4-7-third-party",
    })
  })
})
