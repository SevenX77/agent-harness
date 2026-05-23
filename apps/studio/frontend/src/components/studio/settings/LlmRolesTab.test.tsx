import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { CredentialsState, RolesData } from "../../../api/llm"
import { LlmRolesTab, ModelSettingsDialog, ModelSettingsFields } from "./LlmRolesTab"
import {
  AvailableModelsSidebar,
  buildAvailableModelGroups,
  filterAvailableModelGroups,
} from "./llm-roles/AvailableModelsSidebar"

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
    expect(html).toContain("Add Role")
    expect(html).toContain("Add model")
    expect(html).toContain("Add provider")
    expect(html).not.toContain('aria-label="LLM roles"')
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
    expect(html).toContain("lg:grid-cols-[minmax(0,1fr)_minmax(14rem,20vw)]")
    expect(html).toContain("2xl:grid-cols-[minmax(0,1fr)_minmax(14rem,18rem)]")
    expect(html).not.toContain("lg:grid-cols-[minmax(0,1fr)_18rem]")
  })

  it("uses shadcn select primitives for role controls", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-slot="select-trigger"')
    expect(html).not.toContain('class="mt-1 h-8 rounded-md border border-input bg-background px-2 text-xs"')
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
    expect(triggerHtml).toContain('aria-label="Model settings for CL46T"')
    expect(fieldsHtml).toContain('data-slot="field-set"')
    expect(fieldsHtml).toContain("Temperature")
    expect(fieldsHtml).toContain("Max Tokens")
    expect(fieldsHtml).toContain("Blank uses system default 0.7")
    expect(fieldsHtml).not.toContain('placeholder="Default (System: 0.7)"')
  })
})
