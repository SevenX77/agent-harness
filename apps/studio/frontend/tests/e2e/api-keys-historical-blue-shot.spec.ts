// Real-frontend verification + handbook screenshot for the BLUE historical_ready
// state (gap #3 positive proof): after the backend promotes probe-verified draft
// evidence onto a credential route that is NOT verified this session, the API Keys
// page must render that route as the blue "Previously Connected" badge.
//
// This drives the REAL running app (Vite) + the REAL ProviderCard, mocking only
// GET /api/llm/registry so a route carries ui_state:"historical_ready" — exactly
// what the backend now projects (asserted at contract level in
// test_endpoint_test_promotes_probe_verified_draft_capabilities_and_profiles).
import { expect, test, type Page, type Route } from "@playwright/test"

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5173"

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) })
}

// One official endpoint reachable (verified), one route that is only
// unverified_manual THIS session but historically probe-verified in the draft
// library -> projected ui_state "historical_ready" (blue).
const registry = {
  provider_endpoints: {
    "openai-historical": {
      endpoint_id: "openai-historical",
      display_name: "OpenAI (historical)",
      protocol: "openai_compatible",
      provider_kind: "official",
      base_url: "https://api.openai.example/v1",
      api_key: "sk-historical",
      status: "verified",
      last_test_at: "2026-06-23T00:00:00Z",
      last_test_message: "Catalog reachable.",
      timeout_seconds: 120,
      trust_env: false,
      proxy_env: null,
      metadata: {},
    },
  },
  provider_routes: {
    "openai-historical:gpt-5": {
      route_id: "openai-historical:gpt-5",
      endpoint_id: "openai-historical",
      route_slug: "gpt-5",
      provider_model_id: "gpt-5",
      canonical_id: "gpt-5",
      display_name: "gpt-5",
      status: "unverified_manual",
      ui_state: "historical_ready",
      capabilities: {
        max_context_tokens: { value: 128000, source: "probed_verified" },
      },
      verified_profiles: [],
      metadata: {},
    },
  },
  runtime_policy: { provider_down_ttl_seconds: 60, probe_timeout_seconds: 5, token_escalation_rounds: 2 },
  model_profiles: {},
  model_groups: [],
  roles: {},
  canonical_groups: [],
  lint_results: [],
  setup_required: false,
}

async function mockBackend(page: Page) {
  await page.route("**/api/skills", (route) => fulfillJson(route, []))
  await page.route("**/api/settings", (route) =>
    fulfillJson(route, { user_id: "e2e", gitea_host: "", default_skills_directory: "/tmp/skills" }),
  )
  await page.route("**/api/llm/credentials**", (route) => fulfillJson(route, { providers: [] }))
  await page.route("**/api/llm/roles**", (route) =>
    fulfillJson(route, { models: {}, providers: {}, roles: {}, single_model_roles: [], peer_model_groups: {}, circuit_breaker: null }),
  )
  await page.route("**/api/llm/registry/endpoints", (route) => fulfillJson(route, registry))
  await page.route("**/api/llm/registry", (route) => fulfillJson(route, registry))
}

test.use({ viewport: { width: 1680, height: 1020 } })

test("API Keys renders the blue 'Previously Connected' (historical_ready) state", async ({ page }) => {
  await mockBackend(page)
  await page.goto("about:blank")
  await page.goto(`${baseURL}/#/`)
  await page.getByRole("button", { name: "Settings" }).click()
  await page.getByRole("button", { name: "API Keys", exact: true }).click()
  await expect(page.getByTestId("api-keys-list")).toBeVisible()

  // The real ProviderCard projects route.ui_state -> the blue badge.
  const badge = page.locator('[data-provider-state-label="historical_ready"]').first()
  await expect(badge).toBeVisible()
  await expect(page.getByText("Previously Connected").first()).toBeVisible()

  await page.screenshot({ path: "test-results/api-keys-historical-blue.png", fullPage: true })
})
