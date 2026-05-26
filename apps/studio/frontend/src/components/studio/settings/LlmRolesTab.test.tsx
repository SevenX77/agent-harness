import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { CredentialsState, RolesData } from "../../../api/llm"
import { AvailableModelDragPreview, LlmRolesTab, ModelSettingsDialog, ModelSettingsFields } from "./LlmRolesTab"
import {
  AvailableModelsSidebar,
  buildAvailableModelGroups,
  filterAvailableModelGroups,
} from "./llm-roles/AvailableModelsSidebar"
import { roleNameDisplayError, RoleNameDialog, RoleNameFields } from "./llm-roles/RoleNameDialog"
import { appendAvailableModelToRole, appendRole, normalizeRolesDraft, pruneInvalidRoleProviders, removeRole, renameRole, validateRolesDraft } from "./role-utils"

const credentials: CredentialsState = {
  providers: [
    {
      id: "anthropic",
      name: "Anthropic",
      api_key: "sk-anthropic",
      available_models: [
        { id: "claude-opus-4-1", capabilities: { thinking: true } },
      ],
    },
    {
      id: "openrouter",
      name: "OpenRouter",
      api_key: "sk-openrouter",
      base_url: "https://openrouter.ai/api/v1",
      available_models: [
        { id: "~anthropic/claude-opus-4-1", capabilities: { thinking: true } },
        { id: "~anthropic/claude-sonnet-latest" },
        { id: "~anthropic/claude-3.5-haiku" },
      ],
    },
    {
      id: "openai_proxy",
      name: "OpenAI Proxy",
      api_key: "",
      available_models: [
        { id: "gpt-5", capabilities: { thinking: true } },
        { id: "deepseek-chat" },
      ],
    },
    {
      id: "gemini-official",
      name: "Gemini Official",
      api_key: "sk-gemini",
      available_models: [
        { id: "gemini-3.1-pro-preview" },
      ],
    },
  ],
}

const rolesData: RolesData = {
  models: {
    CL46T: {
      name: "Claude Sonnet 4.6 Thinking",
      providers: { anthropic: "claude-sonnet-4.6", openai_proxy: "anthropic/claude-sonnet-4.6" },
    },
    DS32R: {
      name: "DeepSeek V4 Pro",
      providers: { openai_proxy: "deepseek-v4-pro" },
    },
    GPT5: {
      name: "GPT-5",
      providers: { openai_proxy: "gpt-5" },
    },
  },
  providers: {
    anthropic: { name: "Anthropic", type: "anthropic_compatible" },
    openai_proxy: { name: "OpenAI Proxy", type: "openai_compatible" },
  },
  roles: {
    copilot_chat: {
      model_fallback: true,
      active_model: "CL46T",
      models: {
        CL46T: { providers: ["anthropic"], temperature: 0.2, max_tokens: 8192 },
        DS32R: { providers: ["openai_proxy"], temperature: null, max_tokens: null },
      },
    },
  },
}

function renderRolesHtml(overrides: Partial<Parameters<typeof LlmRolesTab>[0]> = {}) {
  return renderToStaticMarkup(
    <LlmRolesTab
      data={rolesData}
      credentials={credentials}
      saveStatus="idle"
      error={null}
      onChange={vi.fn()}
      {...overrides}
    />,
  )
}

describe("LlmRolesTab controls", () => {
  it("uses skeleton placeholders while roles are loading", () => {
    const html = renderRolesHtml({ data: null })
    const skeletons = html.match(/data-slot="skeleton"/g) ?? []

    expect(skeletons.length).toBeGreaterThan(3)
    expect(html).not.toContain("Loading roles...")
  })

  it("uses shadcn switch primitives and auto-save status instead of manual Save", () => {
    const html = renderRolesHtml({ saveStatus: "pending" })

    expect(html).toContain("Pending")
    expect(html).toContain('data-slot="switch"')
    expect(html).not.toContain('data-slot="checkbox"')
    expect(html).not.toContain(">Save</button>")
    expect(html).not.toContain("Dirty")
  })

  it("renders roles as flat cards with add controls instead of top role tabs", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-slot="card"')
    expect(html).toContain("Add Graph Agent Role")
    expect(html).toContain("Add Copilot Role")
    expect(html).toContain('data-role-add-trigger="true"')
    expect(html).toContain('data-slot="empty"')
    expect(html).toContain("Drop model")
    expect(html).toContain("Add provider")
    expect(html).not.toContain('aria-label="LLM roles"')
    expect(html).not.toContain('aria-label="Add model to role"')
  })

  it("renders the model library as an unframed searchable scroll area", () => {
    const html = renderToStaticMarkup(<AvailableModelsSidebar credentials={credentials} />)

    expect(html).toContain("Available Models")
    expect(html).toContain('data-available-model-count="true"')
    expect(html).toContain('aria-label="6 available models"')
    expect(html).toContain('data-slot="input-group"')
    expect(html).toContain('data-slot="input-group-control"')
    expect(html).toContain('aria-label="Search available models"')
    expect(html).toContain('aria-label="Clear model search"')
    expect(html).toContain('data-slot="scroll-area"')
    expect(html).toContain("[&amp;_[data-slot=scroll-area-scrollbar]]:hidden")
    expect(html).not.toContain('data-slot="card"')
    expect(html).not.toContain("Reference library. Add models from each role card.")
  })

  it("uses the shared card surface with background hover and selected ring treatment", () => {
    const html = renderToStaticMarkup(<AvailableModelsSidebar credentials={credentials} />)

    expect(html).toContain("bg-card")
    expect(html).toContain("ring-inset")
    expect(html).toContain("ring-1 ring-foreground/10")
    expect(html).toContain("hover:bg-muted/25")
    expect(html).toContain("active:scale-[0.99]")
    expect(html).toContain("active:bg-muted/40")
    expect(html).toContain("transition-[background-color,box-shadow,transform]")
    expect(html).toContain("data-[selected=true]:bg-muted/30")
    expect(html).toContain("data-[selected=true]:ring-2")
    expect(html).toContain("data-[selected=true]:ring-primary/70")
    expect(html).toContain("focus-visible:ring-2")
    expect(html).not.toContain("hover:ring-2")
    expect(html).not.toContain("hover:ring-primary/70")
    expect(html).not.toContain("bg-primary/10")
    expect(html).not.toContain("border-primary")
  })

  it("renders thinking as a small brain badge with adaptive text", () => {
    const html = renderToStaticMarkup(<AvailableModelsSidebar credentials={credentials} />)

    expect(html).toContain('aria-label="Thinking capable"')
    expect(html).toContain('data-thinking-badge="true"')
    expect(html).toContain("Thinking")
    expect(html).toContain("text-[9px]")
    expect(html).toContain("hidden xl:inline")
    expect(html).not.toContain("BrainCircuit")
  })

  it("makes available model cards pointer-draggable for role drop targets", () => {
    const html = renderToStaticMarkup(<AvailableModelsSidebar credentials={credentials} />)

    expect(html).toContain('data-available-model-drag-source="true"')
    expect(html).toContain('data-available-model-pointer-drag-source="true"')
  })

  it("renders a pointer drag preview for available model drops", () => {
    const html = renderToStaticMarkup(
      <AvailableModelDragPreview
        drag={{
          dragging: true,
          modelId: "anthropic/claude-opus-4.7",
          x: 120,
          y: 240,
        }}
      />,
    )

    expect(html).toContain('data-available-model-drag-preview="true"')
    expect(html).toContain("anthropic/claude-opus-4.7")
    expect(html).toContain("translate3d(120px, 240px, 0)")
    expect(html).toContain("pointer-events-none")
    expect(html).toContain("ring-primary/40")
  })

  it("renders provider labels as badges without native model/provider title tooltips", () => {
    const html = renderToStaticMarkup(<AvailableModelsSidebar credentials={credentials} />)

    expect(html).toContain('data-available-model-provider-label="true"')
    expect(html).toContain('data-variant="outline"')
    expect(html).toContain("OpenRouter")
    expect(html).not.toContain('title="OpenRouter"')
    expect(html).not.toContain('title="claude-opus-4-1"')
  })

  it("uses a readable overflow count instead of truncating every provider label", () => {
    const manyProviderCredentials: CredentialsState = {
      providers: ["OpenRouter", "QiNiu-Anthropic", "QiNiu-DeepSeek", "team-a", "team-b"].map((name, index) => ({
        id: `provider-${index}`,
        name,
        api_key: "sk-test",
        available_models: [{ id: "deepseek-r1" }],
      })),
    }
    const html = renderToStaticMarkup(<AvailableModelsSidebar credentials={manyProviderCredentials} />)

    expect(html).toContain("OpenRouter")
    expect(html).toContain("QiNiu-Anthropic")
    expect(html).toContain("+3")
    expect(html).not.toContain("shrink truncate")
    expect(html).not.toContain("Ope...")
  })

  it("builds the model library from tested provider available_models instead of role abbreviations", () => {
    const groups = buildAvailableModelGroups(credentials)
    const allModels = groups.flatMap((group) => group.models)
    const html = renderToStaticMarkup(<AvailableModelsSidebar credentials={credentials} />)

    expect(allModels.map((model) => model.id)).toEqual([
      "claude-3.5-haiku",
      "claude-opus-4-1",
      "claude-sonnet-latest",
      "deepseek-chat",
      "gemini-3.1-pro-preview",
      "gpt-5",
    ])
    expect(groups.map((group) => group.vendor)).toEqual(["anthropic", "deepseek", "gemini", "openai"])
    expect(allModels.find((model) => model.id === "claude-opus-4-1")?.providers.map((provider) => provider.label)).toEqual(["Anthropic", "OpenRouter"])
    expect(allModels.find((model) => model.id === "gpt-5")?.providers.map((provider) => provider.label)).toEqual(["OpenAI Proxy"])
    expect(allModels.find((model) => model.id === "gpt-5")?.thinking).toBe(true)
    expect(html).toContain("gpt-5")
    expect(html).not.toContain("~anthropic/claude-opus-4-1")
    expect(html).toContain("Gemini Official")
    expect(html).toContain('aria-label="Thinking capable"')
    expect(html).not.toContain("Providers")
    expect(html).not.toContain("GPT5")
    expect(html).not.toContain("Claude Sonnet 4.6 Thinking")
  })

  it("filters available models by vendor, exact model id, and provider label", () => {
    const groups = buildAvailableModelGroups(credentials)

    expect(filterAvailableModelGroups(groups, "gemini").flatMap((group) => group.models.map((model) => model.id))).toEqual(["gemini-3.1-pro-preview"])
    expect(filterAvailableModelGroups(groups, "gpt5").flatMap((group) => group.models.map((model) => model.id))).toEqual(["gpt-5"])
    expect(filterAvailableModelGroups(groups, "claude 3 5").flatMap((group) => group.models.map((model) => model.id))).toEqual(["claude-3.5-haiku"])
    expect(filterAvailableModelGroups(groups, "claude.opus 4").flatMap((group) => group.models.map((model) => model.id))).toEqual(["claude-opus-4-1"])
    expect(filterAvailableModelGroups(groups, "openrouter").flatMap((group) => group.models.map((model) => model.id))).toEqual(["claude-3.5-haiku", "claude-opus-4-1", "claude-sonnet-latest"])
    expect(filterAvailableModelGroups(groups, "openai proxy").flatMap((group) => group.models.map((model) => model.id))).toEqual(["deepseek-chat", "gpt-5"])
    expect(filterAvailableModelGroups(groups, "missing")).toEqual([])
  })

  it("keeps the title inside the roles scroll area and the model library beside it", () => {
    const html = renderRolesHtml()
    const rolesScrollAreaStart = html.indexOf('data-slot="scroll-area"')
    const rolesViewportStart = html.indexOf('data-slot="scroll-area-viewport"', rolesScrollAreaStart)
    const modelsSidebarStart = html.indexOf("<aside", rolesViewportStart)
    const rolesViewportHtml = html.slice(rolesViewportStart, modelsSidebarStart)

    expect(rolesViewportHtml).toContain("LLM Roles")
    expect(rolesViewportHtml).toContain('data-role-name="copilot_chat"')
    expect(rolesViewportHtml).not.toContain("Available Models")
    expect(html.indexOf("Available Models")).toBeGreaterThan(modelsSidebarStart)
    expect(html.slice(rolesScrollAreaStart, rolesViewportStart)).toContain("[&amp;_[data-slot=scroll-area-scrollbar]]:hidden")
    expect(html).toContain("lg:grid-cols-[minmax(0,1fr)_minmax(14rem,20vw)]")
    expect(html).toContain("2xl:grid-cols-[minmax(0,1fr)_minmax(14rem,18rem)]")
    expect(html).not.toContain("lg:grid-cols-[minmax(0,1fr)_18rem]")
  })

  it("uses shadcn dropdown primitives for provider add controls", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-slot="dropdown-menu-trigger"')
    expect(html).toContain('data-provider-add-trigger="true"')
    expect(html).not.toContain('aria-label="Add provider to model"')
    expect(html).not.toContain('data-slot="select-trigger"')
    expect(html).not.toContain('class="mt-1 h-8 rounded-md border border-input bg-background px-2 text-xs"')
  })

  it("keeps model row content centered with breathing room between title and badges", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-model-row="true"')
    expect(html).toContain("items-center")
    expect(html).toContain('data-model-title-row="true"')
    expect(html).toContain('data-model-badge-group="true"')
    expect(html).toContain("grid-cols-[minmax(0,max-content)_auto]")
    expect(html).toContain("gap-x-4")
    expect(html).toContain("gap-2.5")
  })

  it("keeps provider names single-line with a tooltip for overflow", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-provider-title-tooltip="true"')
    expect(html).toContain("truncate")
    expect(html).toContain("whitespace-nowrap")
    expect(html).toContain("flex-nowrap")
  })

  it("prevents text selection on every draggable surface", () => {
    const html = renderRolesHtml()
    const availableModelsHtml = renderToStaticMarkup(<AvailableModelsSidebar credentials={credentials} />)

    expect(html).toContain('data-dnd-drag-surface="model"')
    expect(html).toContain('data-dnd-drag-surface="provider"')
    expect(html).toContain("select-none")
    expect(availableModelsHtml).toContain('data-available-model-drag-source="true"')
    expect(availableModelsHtml).toContain("select-none")
  })

  it("accepts available model drops across the role card content area", () => {
    const html = renderRolesHtml()

    expect(html).toMatch(/data-slot="card"[^>]*data-role-name="copilot_chat"[^>]*data-model-drop-zone="true"/)
    expect(html).toContain('data-model-drop-zone="true"')
    expect(html).toContain('data-model-drop-target="true"')
    expect(html).toContain('data-model-drop-fallback="active-drag-ref"')
    expect(html).toContain('data-role-drop-shield="true"')
  })

  it("renders provider rows as capped-width grid tracks with a ghost dropdown button", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-provider-grid="true"')
    expect(html).toContain("grid-cols-[repeat(auto-fill,minmax(min(100%,12rem),20rem))]")
    expect(html).toContain("justify-start")
    expect(html).not.toContain("grid-cols-[repeat(auto-fit,minmax(min(100%,max(12rem,calc((100%_-_0.75rem)/3))),1fr))]")
    expect(html).not.toContain("grid-cols-[repeat(auto-fit,minmax(12rem,1fr))]")
    expect(html).toContain('data-provider-add-trigger="true"')
    expect(html).toContain('data-variant="ghost"')
    expect(html).toContain("h-9 w-full")
    expect(html).toContain("hover:bg-muted/35")
    expect(html).toContain("Add provider")
    expect(html).not.toContain("All providers added")

    const allProvidersAddedData: RolesData = {
      ...rolesData,
      roles: {
        copilot_chat: {
          ...rolesData.roles.copilot_chat,
          models: {
            CL46T: {
              ...rolesData.roles.copilot_chat.models.CL46T,
              providers: ["anthropic", "openai_proxy"],
            },
          },
        },
      },
    }
    const filledHtml = renderRolesHtml({ data: allProvidersAddedData })

    expect(filledHtml).not.toContain('data-provider-add-trigger="true"')
  })

  it("uses subdued provider card text and role editor icons", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-provider-title-tooltip="true"')
    expect(html).toContain("text-muted-foreground")
    expect(html).toContain('data-role-icon="true"')
  })

  it("adds named roles as empty drafts that can auto-save", () => {
    const next = appendRole(rolesData, "planner_role")

    expect(Object.keys(next.roles)).toEqual(["copilot_chat", "planner_role"])
    expect(next.roles.planner_role).toEqual({
      model_fallback: true,
      active_model: "",
      models: {},
    })
    expect(validateRolesDraft(next)).toBeNull()
  })

  it("normalizes stale active models before roles autosave", () => {
    const next = normalizeRolesDraft({
      ...rolesData,
      roles: {
        ...rolesData.roles,
        test: {
          model_fallback: true,
          active_model: "unknown model",
          models: {},
        },
        stale_model: {
          model_fallback: true,
          active_model: "unknown model",
          models: {
            "unknown model": { providers: [] },
          },
        },
      },
    })

    expect(next.roles.test.active_model).toBe("")
    expect(next.roles.stale_model.active_model).toBe("")
    expect(next.roles.stale_model.models).toEqual({})
    expect(validateRolesDraft(next)).toBeNull()
  })

  it("renames role keys without changing role configuration", () => {
    const dataWithSingleModelRole: RolesData = {
      ...rolesData,
      single_model_roles: ["copilot_chat"],
    }

    const next = renameRole(dataWithSingleModelRole, "copilot_chat", "planner_role")

    expect(Object.keys(next.roles)).toEqual(["planner_role"])
    expect(next.roles.planner_role).toEqual(rolesData.roles.copilot_chat)
    expect(next.roles.copilot_chat).toBeUndefined()
    expect(next.single_model_roles).toEqual(["planner_role"])
  })

  it("uses a role name dialog for add and edit flows", () => {
    const html = renderRolesHtml()
    const dialogHtml = renderToStaticMarkup(
      <RoleNameDialog
        title="New role"
        initialName=""
        existingNames={Object.keys(rolesData.roles)}
        open
        trigger={<button type="button">Open</button>}
        onSubmit={vi.fn()}
      />,
    )
    const fieldsHtml = renderToStaticMarkup(
      <RoleNameFields
        inputId="role-name-test"
        nameDraft="planner_role"
        error={null}
        onNameChange={vi.fn()}
      />,
    )

    expect(html).toContain('data-role-actions-trigger="true"')
    expect(html).not.toContain(">Edit</button>")
    expect(dialogHtml).toContain('data-slot="dialog-trigger"')
    expect(fieldsHtml).toContain('data-slot="field-set"')
    expect(fieldsHtml).toContain("Role name")
    expect(fieldsHtml).toContain('value="planner_role"')
    expect(dialogHtml).not.toContain("disabled")
  })

  it("groups roles into graph agent and copilot accordion sections", () => {
    const groupedData: RolesData = {
      ...rolesData,
      roles: {
        planner: {
          model_fallback: true,
          active_model: "",
          models: {},
        },
        copilot_chat: rolesData.roles.copilot_chat,
      },
    }
    const html = renderRolesHtml({ data: groupedData })

    expect(html).toContain('data-slot="catalog-accordion"')
    expect(html).toContain('data-slot="catalog-accordion-trigger"')
    expect(html).toContain('data-role-category="graph-agent"')
    expect(html).toContain("Graph Agent Roles")
    expect(html).toContain('data-role-category="copilot"')
    expect(html).toContain("Copilot Roles")
    expect(html.indexOf("Graph Agent Roles")).toBeLessThan(html.indexOf("Copilot Roles"))
    expect(html.indexOf("catalog-accordion-state-icon")).toBeLessThan(html.indexOf("Graph Agent Roles"))
    expect(html.indexOf("Graph Agent Roles")).toBeLessThan(html.indexOf("lucide-cog"))
    expect(html).not.toContain("lucide-workflow")
  })

  it("uses role_kind instead of role name when grouping roles", () => {
    const groupedData: RolesData = {
      ...rolesData,
      roles: {
        assistant: {
          role_kind: "copilot",
          model_fallback: true,
          active_model: "",
          models: {},
        },
        copilot_planner: {
          role_kind: "graph_agent",
          model_fallback: true,
          active_model: "",
          models: {},
        },
      },
    }
    const html = renderRolesHtml({ data: groupedData })
    const graphSectionStart = html.indexOf('data-role-category="graph-agent"')
    const copilotSectionStart = html.indexOf('data-role-category="copilot"')
    const graphSection = html.slice(graphSectionStart, copilotSectionStart)
    const copilotSection = html.slice(copilotSectionStart)

    expect(graphSection).toContain('data-role-name="copilot_planner"')
    expect(graphSection).not.toContain('data-role-name="assistant"')
    expect(copilotSection).toContain('data-role-name="assistant"')
  })

  it("keeps empty role categories visible and uses default title typography", () => {
    const graphOnlyData: RolesData = {
      ...rolesData,
      roles: {
        Premium: {
          model_fallback: true,
          active_model: "",
          models: {},
        },
      },
    }
    const html = renderRolesHtml({ data: graphOnlyData })
    const titleIndex = html.indexOf('data-slot="card-title"')
    const titleEnd = html.indexOf("</div>", titleIndex)
    const titleHtml = html.slice(titleIndex, titleEnd)

    expect(html).toContain('data-role-category="graph-agent"')
    expect(html).toContain('data-role-category="copilot"')
    expect(html).toContain("No Copilot roles configured.")
    expect(html).toContain("Add Graph Agent Role")
    expect(html).toContain("Add Copilot Role")
    expect(titleHtml).not.toContain("font-mono")
  })

  it("uses a role title icon and dropdown actions for edit and delete", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-role-title-icon="true"')
    expect(html).toContain('data-role-actions-trigger="true"')
    expect(html).toContain('aria-label="More actions for copilot_chat"')
    expect(html).not.toContain('data-role-edit-trigger="true"')
    expect(html).not.toContain(">Edit</button>")
  })

  it("removes role entries from role maps and grouping metadata", () => {
    const dataWithMetadata: RolesData = {
      ...rolesData,
      single_model_roles: ["copilot_chat"],
      peer_model_groups: {
        default: ["copilot_chat", "planner"],
      },
      roles: {
        ...rolesData.roles,
        planner: {
          model_fallback: true,
          active_model: "",
          models: {},
        },
      },
    }

    const next = removeRole(dataWithMetadata, "copilot_chat")

    expect(next.roles.copilot_chat).toBeUndefined()
    expect(next.roles.planner).toBeTruthy()
    expect(next.single_model_roles).toEqual([])
    expect(next.peer_model_groups).toEqual({ default: ["planner"] })
  })

  it("does not show role name errors until submit and checks duplicates case-insensitively", () => {
    expect(roleNameDisplayError("", ["copilot_chat"], "", false)).toBeNull()
    expect(roleNameDisplayError("copilot_chat", ["copilot_chat"], "", false)).toBeNull()
    expect(roleNameDisplayError("", ["copilot_chat"], "", true)).toBe("Role name is required.")
    expect(roleNameDisplayError("copilot_chat", ["copilot_chat"], "", true)).toBe("Role name already exists.")
    expect(roleNameDisplayError("Copilot_Chat", ["copilot_chat"], "", true)).toBe("Role name already exists.")
  })

  it("keeps role fallback controls in the right header action group", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-role-card-title-row="true"')
    expect(html).toContain('data-role-header-actions="true"')
    expect(html).toContain("items-center")
    expect(html).toContain("self-center")
    expect(html).toContain("row-span-1")
    expect(html).toContain("flex-nowrap")
    expect(html).toContain("h-8")
    expect(html).toContain("justify-self-end")
    expect(html).toContain("model_fallback")
    expect(html).toContain('data-role-test-trigger="true"')
  })

  it("lazy renders available model cards without changing the full result count", () => {
    const manyModelsCredentials: CredentialsState = {
      providers: [{
        id: "bulk-provider",
        name: "Bulk Provider",
        api_key: "sk-bulk",
        available_models: Array.from({ length: 50 }, (_, index) => ({ id: `bulk-model-${index}` })),
      }],
    }
    const html = renderToStaticMarkup(<AvailableModelsSidebar credentials={manyModelsCredentials} />)
    const renderedCards = html.match(/data-available-model-drag-source="true"/g) ?? []

    expect(html).toContain('data-lazy-list="available-models"')
    expect(html).toContain('data-lazy-sentinel="available-models"')
    expect(html).toContain('aria-label="50 available models"')
    expect(renderedCards.length).toBeGreaterThan(0)
    expect(renderedCards.length).toBeLessThan(50)
  })

  it("lazy renders role cards before the add-role action", () => {
    const manyRolesData: RolesData = {
      ...rolesData,
      roles: Object.fromEntries(
        Array.from({ length: 12 }, (_, index) => [
          `role_${index}`,
          {
            model_fallback: true,
            active_model: "CL46T",
            models: {
              CL46T: { providers: ["anthropic"], temperature: null, max_tokens: null },
            },
          },
        ]),
      ),
    }
    const html = renderRolesHtml({ data: manyRolesData })
    const renderedRoles = html.match(/data-role-name="/g) ?? []

    expect(html).toContain('data-lazy-list="roles"')
    expect(html).toContain('data-lazy-sentinel="roles"')
    expect(renderedRoles.length).toBeGreaterThan(0)
    expect(renderedRoles.length).toBeLessThan(12)
    expect(html).toContain("Add Graph Agent Role")
    expect(html).toContain("Add Copilot Role")
  })

  it("shows readable model names instead of active model controls or model abbreviations", () => {
    const html = renderRolesHtml()

    expect(html).toContain("Claude Sonnet 4.6 Thinking")
    expect(html).toContain("DeepSeek V4 Pro")
    expect(html).not.toContain("configured for this model")
    expect(html).not.toContain("Provider chain")
    expect(html).not.toContain("Active model")
    expect(html).not.toContain("First model attempted before fallback.")
    expect(html).not.toContain(">CL46T<")
    expect(html).not.toContain(">DS32R<")
    expect(html).not.toContain(">GPT5<")
    expect(html).not.toContain(">active<")
  })

  it("filters role providers to the providers owned by that model", () => {
    const dataWithMismatchedProvider: RolesData = {
      ...rolesData,
      providers: {
        ...rolesData.providers,
        gemini: { name: "Gemini Official", type: "google_genai" },
      },
      models: {
        ...rolesData.models,
        CL46T: {
          ...rolesData.models.CL46T,
          name: "claude-opus-4-1",
          providers: {
            anthropic: "claude-opus-4-1",
            gemini: "gemini-3.1-pro-preview",
          },
        },
      },
      roles: {
        copilot_chat: {
          ...rolesData.roles.copilot_chat,
          models: {
            CL46T: { providers: ["anthropic", "gemini"], temperature: 0.2, max_tokens: 8192 },
          },
        },
      },
    }
    const html = renderRolesHtml({ data: dataWithMismatchedProvider })
    const roleCardStart = html.indexOf('data-role-name="copilot_chat"')
    const sidebarStart = html.indexOf("<aside", roleCardStart)
    const roleCardHtml = html.slice(roleCardStart, sidebarStart)

    expect(roleCardHtml).toContain("Anthropic")
    expect(roleCardHtml).not.toContain("Gemini Official")
  })

  it("materializes credential providers when adding available models to a role", () => {
    const customCredentials: CredentialsState = {
      providers: [{
        id: "custom-532dc361-de53-480e-864f-188d9271ef34",
        name: "Anthropic Custom",
        api_key: "sk-custom",
        base_url: "https://example.test/v1",
        provider_type: "anthropic_compatible",
        available_models: [
          { id: "anthropic/claude-opus-4.7", capabilities: { thinking: true } },
        ],
      }],
    }
    const next = appendAvailableModelToRole(
      rolesData,
      "copilot_chat",
      "anthropic/claude-opus-4.7",
      Object.fromEntries(customCredentials.providers.map((provider) => [provider.id, provider])),
    )
    const modelCode = Object.keys(next.roles.copilot_chat.models)
      .find((code) => next.models[code]?.name === "anthropic/claude-opus-4.7")

    expect(modelCode).toBeTruthy()
    expect(next.providers["custom-532dc361-de53-480e-864f-188d9271ef34"]).toEqual({
      name: "Anthropic Custom",
      type: "anthropic_compatible",
      base_url: "https://example.test/v1",
    })
    expect(next.models[modelCode!].providers).toEqual({
      "custom-532dc361-de53-480e-864f-188d9271ef34": "anthropic/claude-opus-4.7",
    })
    expect(next.roles.copilot_chat.models[modelCode!].providers).toEqual([
      "custom-532dc361-de53-480e-864f-188d9271ef34",
    ])
    expect(validateRolesDraft(next)).toBeNull()
  })

  it("flags unknown role providers before the backend rejects the save", () => {
    const invalidData: RolesData = {
      ...rolesData,
      roles: {
        ...rolesData.roles,
        copilot_chat: {
          ...rolesData.roles.copilot_chat,
          models: {
            CL46T: { providers: ["missing-provider"], temperature: null, max_tokens: null },
          },
        },
      },
    }

    expect(validateRolesDraft(invalidData)).toBe(
      "copilot_chat: Model CL46T references unknown provider missing-provider",
    )
  })

  it("repairs a failed custom-provider draft when credential metadata is available", () => {
    const providerId = "custom-532dc361-de53-480e-864f-188d9271ef34"
    const customCredentials: CredentialsState = {
      providers: [{
        id: providerId,
        name: "Anthropic Custom",
        api_key: "sk-custom",
        base_url: "https://example.test/v1",
        provider_type: "anthropic_compatible",
        available_models: [{ id: "anthropic/claude-opus-4.7" }],
      }],
    }
    const failedDraft: RolesData = {
      ...rolesData,
      models: {
        ...rolesData.models,
        "anthropic/claude-opus-4.7": {
          name: "anthropic/claude-opus-4.7",
          reasoning: true,
          providers: { [providerId]: "anthropic/claude-opus-4.7" },
        },
      },
      roles: {
        copilot_chat: {
          ...rolesData.roles.copilot_chat,
          active_model: "anthropic/claude-opus-4.7",
          models: {
            "anthropic/claude-opus-4.7": { providers: [providerId], temperature: null, max_tokens: null },
          },
        },
      },
    }

    const repaired = pruneInvalidRoleProviders(
      failedDraft,
      Object.fromEntries(customCredentials.providers.map((provider) => [provider.id, provider])),
    )

    expect(repaired.providers[providerId]).toEqual({
      name: "Anthropic Custom",
      type: "anthropic_compatible",
      base_url: "https://example.test/v1",
    })
    expect(repaired.roles.copilot_chat.models["anthropic/claude-opus-4.7"].providers).toEqual([providerId])
    expect(validateRolesDraft(repaired)).toBeNull()
  })

  it("uses whole-row drag surfaces without explicit drag or arrow controls", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-dnd-drag-surface="model"')
    expect(html).toContain('data-dnd-drag-surface="provider"')
    expect(html).toContain('data-slot="item"')
    expect(html).toContain('data-variant="outline"')
    expect(html).toContain('data-variant="muted"')
    expect(html).not.toContain('aria-label="Drag')
    expect(html).not.toContain('aria-label="Move')
  })

  it("uses a primary default-size test button on the role header", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-role-test-trigger="true"')
    expect(html).toContain('data-variant="default"')
    expect(html).toContain('data-size="default"')
    expect(html).toContain("min-w-20")
    expect(html).toContain(">Test</button>")
    expect(html).not.toContain("Test Chain")
  })

  it("uses semantic destructive badges instead of hard-coded red utility colors", () => {
    const html = renderRolesHtml()

    expect(html).toContain("Unavailable")
    expect(html).toContain('data-variant="destructive"')
    expect(html).not.toContain("border-red")
    expect(html).not.toContain("bg-red")
    expect(html).not.toContain("text-red")
  })

  it("renders model settings through Dialog and Field primitives", () => {
    const triggerHtml = renderToStaticMarkup(
      <ModelSettingsDialog
        modelCode="CL46T"
        modelName="Claude Sonnet 4.6 Thinking"
        temperature={0.2}
        maxTokens={8192}
        onSubmit={vi.fn()}
      />,
    )
    const fieldsHtml = renderToStaticMarkup(
      <ModelSettingsFields
        modelCode="CL46T"
        temperatureDraft="0.2"
        maxTokensDraft="8192"
        onTemperatureChange={vi.fn()}
        onMaxTokensChange={vi.fn()}
      />,
    )

    expect(triggerHtml).toContain('data-slot="dialog-trigger"')
    expect(triggerHtml).toContain('aria-label="Model settings for Claude Sonnet 4.6 Thinking"')
    expect(fieldsHtml).toContain('data-slot="field-set"')
    expect(fieldsHtml).toContain("Temperature")
    expect(fieldsHtml).toContain("Max Tokens")
    expect(fieldsHtml).toContain("Blank uses system default 0.7")
    expect(fieldsHtml).not.toContain('placeholder="Default (System: 0.7)"')
  })
})
