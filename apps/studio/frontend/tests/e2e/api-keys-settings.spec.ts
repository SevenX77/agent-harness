import { expect, test, type Page, type Route } from "@playwright/test"

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5173"

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) })
}

const emptyRegistry = {
  provider_endpoints: {},
  provider_routes: {},
  runtime_policy: { provider_down_ttl_seconds: 60, probe_timeout_seconds: 5, token_escalation_rounds: 2 },
  model_profiles: {},
  model_groups: [],
  roles: {},
  canonical_groups: [],
  lint_results: [],
  setup_required: false,
}

interface ApiKeysBackendState {
  endpointPuts: unknown[]
}

async function mockApiKeysBackend(page: Page): Promise<ApiKeysBackendState> {
  const state: ApiKeysBackendState = { endpointPuts: [] }
  await page.route("**/api/skills", (route) => fulfillJson(route, []))
  await page.route("**/api/settings", (route) =>
    fulfillJson(route, { user_id: "e2e", gitea_host: "", default_skills_directory: "/tmp/skills" }),
  )
  await page.route("**/api/llm/credentials**", (route) => fulfillJson(route, { providers: [] }))
  await page.route("**/api/llm/roles**", (route) =>
    fulfillJson(route, { models: {}, providers: {}, roles: {}, single_model_roles: [], peer_model_groups: {}, circuit_breaker: null }),
  )
  await page.route("**/api/llm/registry/endpoints", async (route) => {
    if (route.request().method() === "PUT") {
      state.endpointPuts.push(route.request().postDataJSON())
      await fulfillJson(route, { ...emptyRegistry })
      return
    }
    await fulfillJson(route, { ...emptyRegistry })
  })
  await page.route("**/api/llm/registry", (route) => fulfillJson(route, emptyRegistry))
  return state
}

async function openApiKeys(page: Page) {
  await page.goto("about:blank")
  await page.goto(`${baseURL}/#/`)
  await page.getByRole("button", { name: "Settings" }).click()
  await page.getByRole("button", { name: "API Keys", exact: true }).click()
  await expect(page.getByTestId("api-keys-list")).toBeVisible()
}

test.describe("API Keys settings", () => {
  test("#22 the API key field is a CSS-masked text input, never a native password field", async ({ page }) => {
    await mockApiKeysBackend(page)
    await openApiKeys(page)

    // Official cards always render an API Key input; assert the secret-field contract.
    const apiKeyInput = page.locator('input[id^="api-key-"]').first()
    await expect(apiKeyInput).toBeVisible()
    await expect(apiKeyInput).toHaveAttribute("type", "text")
    await expect(apiKeyInput).toHaveClass(/mask-input/)

    // Toggling visibility never switches to type=password — only the CSS mask drops.
    await page.getByRole("button", { name: "Show API key" }).first().click()
    await expect(apiKeyInput).toHaveAttribute("type", "text")
    await expect(apiKeyInput).not.toHaveClass(/mask-input/)
  })

  test("#19 Add Provider is a one-step inline form (name + base_url + api_key) that saves in one go", async ({ page }) => {
    await mockApiKeysBackend(page)
    await openApiKeys(page)

    await page.getByRole("button", { name: "Add Provider" }).click()
    const form = page.locator('[data-add-provider-form="true"]')
    await expect(form).toBeVisible()
    // One step: all three fields present at once.
    await expect(form.locator("#add-provider-name")).toBeVisible()
    await expect(form.locator("#add-provider-base-url")).toBeVisible()
    await expect(form.locator("#add-provider-api-key")).toBeVisible()
    await page.screenshot({ path: "test-results/api-keys-add-provider.png" })

    await form.locator("#add-provider-name").fill("My OpenRouter")
    await form.locator("#add-provider-base-url").fill("https://openrouter.ai/api")
    await form.locator("#add-provider-api-key").fill("sk-e2e-secret")

    const putRequest = page.waitForRequest(
      (request) => request.url().includes("/api/llm/registry/endpoints") && request.method() === "PUT",
    )
    await form.locator('[data-add-provider-submit="true"]').click()

    // A single submit persists the provider with its URL + key already filled.
    const body = JSON.stringify((await putRequest).postDataJSON())
    expect(body).toContain("https://openrouter.ai/api")
    expect(body).toContain("sk-e2e-secret")
    await expect(form).toBeHidden()
  })

  test("#19 the inline form blocks an empty provider name", async ({ page }) => {
    await mockApiKeysBackend(page)
    await openApiKeys(page)

    await page.getByRole("button", { name: "Add Provider" }).click()
    const form = page.locator('[data-add-provider-form="true"]')
    await form.locator('[data-add-provider-submit="true"]').click()
    await expect(form.getByText("Provider name is required.")).toBeVisible()
    await expect(form).toBeVisible() // not submitted/closed
  })
})
