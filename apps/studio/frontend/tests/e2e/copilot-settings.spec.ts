import { expect, test, type Page, type Route } from "@playwright/test"

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5173"

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) })
}

const credentials = {
  providers: [
    {
      id: "anthropic",
      name: "Anthropic Official",
      api_key: "sk-anthropic",
      base_url: "https://api.anthropic.com",
      provider_type: "anthropic_compatible",
      last_test_status: "ok",
      last_test_at: "2026-05-24T00:00:00Z",
      last_test_message: "",
      last_error_code: "",
      available_sdks: ["anthropic_compatible"],
      available_models: [{ id: "claude-opus-4.8", capabilities: { thinking: true } }],
    },
  ],
}

function modelGroup(canonicalId: string, displayName: string) {
  return {
    canonical_id: canonicalId,
    display_name: displayName,
    provider_models: [
      {
        route_id: `anthropic:${canonicalId}`,
        endpoint_id: "anthropic",
        provider_label: "Anthropic Official",
        provider_kind: "official",
        provider_model_id: canonicalId,
        ui_state: "ready",
        ui_detail: null,
        retry_at: null,
        reason_code: null,
        capability_state: "known",
        capabilities: {},
      },
    ],
    status_summary: { ready: 1, untested: 0, cooling_down: 0, historical_ready: 0, failed: 0, off: 0 },
    capability_summary: {
      capability_known_count: 1,
      thinking: "unknown",
      tools: "unknown",
      structured_output: "unknown",
      max_context_tokens: null,
      max_output_tokens: null,
    },
  }
}

const registry = {
  provider_endpoints: {
    anthropic: {
      endpoint_id: "anthropic",
      display_name: "Anthropic Official",
      protocol: "anthropic_compatible",
      base_url: "https://api.anthropic.com",
      api_key: "sk-anthropic",
      status: "verified",
      last_test_at: "2026-05-24T00:00:00Z",
      last_test_message: "",
      timeout_seconds: 120,
      trust_env: false,
      proxy_env: null,
      metadata: {},
    },
  },
  provider_routes: {},
  runtime_policy: { provider_down_ttl_seconds: 60, probe_timeout_seconds: 5, token_escalation_rounds: 2 },
  model_profiles: {},
  model_groups: [modelGroup("claude-opus-4.8", "Claude Opus 4.8")],
  roles: {},
  canonical_groups: [],
  lint_results: [],
  setup_required: false,
}

const emptyRoles = {
  models: {},
  providers: {},
  roles: {},
  single_model_roles: [],
  peer_model_groups: {},
  circuit_breaker: null,
}

const rolesWithEmptyDraft = {
  ...emptyRoles,
  roles: {
    copilot_custom_1: {
      role_kind: "copilot",
      model_fallback: true,
      active_model: "",
      models: {},
      fallback_chain: [],
    },
  },
}

const rolesWithCopilot = {
  ...emptyRoles,
  models: { "claude-opus-4.8": { name: "claude-opus-4.8", providers: { anthropic: "claude-opus-4.8" } } },
  providers: { anthropic: { name: "Anthropic Official", type: "anthropic_compatible" } },
  roles: {
    copilot_custom_1: {
      role_kind: "copilot",
      model_fallback: true,
      active_model: "claude-opus-4.8",
      models: { "claude-opus-4.8": { providers: ["anthropic:claude-opus-4.8"] } },
      fallback_chain: [{ route_id: "anthropic:claude-opus-4.8", runtime_settings: {} }],
    },
  },
}

interface CopilotBackendState {
  putCount: number
  lastPut: unknown
}

async function mockCopilotBackend(page: Page, rolesBody: object): Promise<CopilotBackendState> {
  const state: CopilotBackendState = { putCount: 0, lastPut: null }
  await page.route("**/api/skills", (route) => fulfillJson(route, []))
  await page.route("**/api/settings", (route) =>
    fulfillJson(route, { user_id: "e2e", gitea_host: "", default_skills_directory: "/tmp/skills" }),
  )
  await page.route("**/api/llm/credentials**", (route) => fulfillJson(route, credentials))
  await page.route("**/api/llm/registry", (route) => fulfillJson(route, registry))
  await page.route("**/api/llm/roles**", async (route) => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname
    if (pathname.endsWith("/test-results")) {
      await fulfillJson(route, { results: {} })
      return
    }
    if (request.method() === "PUT" && pathname === "/api/llm/roles") {
      state.putCount += 1
      state.lastPut = request.postDataJSON()
      await fulfillJson(route, request.postDataJSON())
      return
    }
    await fulfillJson(route, rolesBody)
  })
  return state
}

async function openCopilot(page: Page) {
  await page.goto("about:blank")
  await page.goto(`${baseURL}/#/`)
  await page.getByRole("button", { name: "Settings" }).click()
  await page.getByRole("button", { name: "Copilot", exact: true }).click()
  await expect(page.locator('[data-copilot-settings-page="true"]')).toBeVisible()
}

test.describe("Copilot settings", () => {
  test("#56 floats the built-in default when no copilot role exists, without persisting it", async ({ page }) => {
    const state = await mockCopilotBackend(page, emptyRoles)
    await openCopilot(page)

    const builtIn = page.locator('[data-copilot-role-source="built_in"]')
    await expect(builtIn).toBeVisible()
    await expect(builtIn.getByText("Built-in")).toBeVisible()
    // Render-only float (atom-56 ①): no auto-PUT on mount.
    await page.waitForTimeout(500)
    expect(state.putCount).toBe(0)
    await page.screenshot({ path: "test-results/copilot-float.png" })
  })

  test("#63 empty draft uses a searchable combobox to pick a model group", async ({ page }) => {
    const state = await mockCopilotBackend(page, rolesWithEmptyDraft)
    await openCopilot(page)

    // The pre-existing empty draft renders the combobox picker card.
    const emptyCard = page.locator('[data-copilot-empty-role-card="true"]')
    await expect(emptyCard).toBeVisible()

    await emptyCard.locator('[data-copilot-model-group-select="true"]').click()
    const search = page.locator('[data-copilot-model-group-search="true"]')
    await expect(search).toBeVisible()
    // Searchable: a non-matching query hides the option, a matching one shows it.
    await search.fill("zzz-no-match")
    await expect(page.locator('[data-copilot-model-option="claude-opus-4.8"]')).toHaveCount(0)
    await search.fill("opus")
    await expect(page.locator('[data-copilot-model-option="claude-opus-4.8"]')).toBeVisible()
    await page.screenshot({ path: "test-results/copilot-combobox.png" })

    // The selection wiring (applyCopilotModelGroupSelection: keeps the copilot_ role key
    // and writes the model group) is covered at the unit level in
    // copilot-role-derivation.test.ts — cmdk item selection is not reliably driveable in
    // headless Playwright, so this e2e asserts only the searchable picker behaviour.
    void state
  })

  test("#61 group Remove deselects the model group back to an empty card", async ({ page }) => {
    const state = await mockCopilotBackend(page, rolesWithCopilot)
    await openCopilot(page)

    const removeButton = page.locator('[data-copilot-model-group-remove="true"]')
    await expect(removeButton).toBeEnabled()
    await removeButton.click()

    // Deselecting returns the role to the empty (re-selectable) card and persists.
    // The role itself is kept (role_kind copilot) — only its model group is cleared (#61 vs #64).
    await expect(page.locator('[data-copilot-empty-role-card="true"]')).toBeVisible()
    await expect.poll(() => state.putCount).toBeGreaterThan(0)
    const put = state.lastPut as { roles?: Record<string, { role_kind?: string; model_groups?: unknown[] }> }
    expect(put.roles?.copilot_custom_1?.role_kind).toBe("copilot")
    expect(put.roles?.copilot_custom_1?.model_groups).toEqual([])
  })
})
