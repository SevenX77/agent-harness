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

const emptyRoles = {
  models: {},
  providers: {},
  roles: {},
  single_model_roles: [],
  peer_model_groups: {},
  circuit_breaker: null,
}

interface ShellBackendState {
  registryGets: number
  rolesGets: number
}

async function mockShellBackend(page: Page): Promise<ShellBackendState> {
  const state: ShellBackendState = { registryGets: 0, rolesGets: 0 }
  await page.route("**/api/skills", (route) => fulfillJson(route, []))
  await page.route("**/api/settings", (route) =>
    fulfillJson(route, { user_id: "e2e", gitea_host: "", default_skills_directory: "/tmp/skills" }),
  )
  await page.route("**/api/llm/credentials**", (route) => fulfillJson(route, { providers: [] }))
  await page.route("**/api/llm/roles**", (route) => {
    if (route.request().method() === "GET") state.rolesGets += 1
    return fulfillJson(route, emptyRoles)
  })
  await page.route("**/api/llm/registry", (route) => {
    if (route.request().method() === "GET") state.registryGets += 1
    return fulfillJson(route, emptyRegistry)
  })
  return state
}

/**
 * MockWebSocket exposing a window-level control handle (`window.__wsControl`) so
 * the test can push server events (registry_changed / roles_changed), deliver a
 * raw (malformed) frame, and drop the live socket. When `window.__wsAutoOpen` is
 * false every new socket fails to open (server unreachable), so the hook's
 * reconnect backoff keeps failing — used to drive the connection-lost threshold.
 */
async function installMockWebSocket(page: Page) {
  await page.addInitScript(() => {
    const OPEN = 1
    const CLOSED = 3
    const instances: Array<{
      readyState: number
      onopen: ((e: Event) => void) | null
      onclose: ((e: CloseEvent) => void) | null
      onerror: ((e: Event) => void) | null
      onmessage: ((e: MessageEvent) => void) | null
    }> = []

    const w = window as unknown as {
      __wsAutoOpen?: boolean
      __wsControl?: { pushLast: (event: unknown) => void; deliverRawToLast: (raw: string) => void; dropLast: () => void }
    }
    w.__wsAutoOpen = true

    class MockWebSocket extends EventTarget {
      static readonly CONNECTING = 0
      static readonly OPEN = 1
      static readonly CLOSING = 2
      static readonly CLOSED = 3

      readonly url: string
      readyState = MockWebSocket.CONNECTING
      onopen: ((event: Event) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null

      constructor(url: string) {
        super()
        this.url = url
        instances.push(this)
        window.setTimeout(() => {
          if (w.__wsAutoOpen === false) {
            this.readyState = MockWebSocket.CLOSED
            this.onerror?.(new Event("error"))
            this.onclose?.(new CloseEvent("close"))
            return
          }
          this.readyState = MockWebSocket.OPEN
          this.onopen?.(new Event("open"))
        }, 0)
      }

      send() {}

      close() {
        this.readyState = MockWebSocket.CLOSED
        this.onclose?.(new CloseEvent("close"))
      }
    }

    Object.defineProperty(MockWebSocket, "OPEN", { value: 1 })
    window.WebSocket = MockWebSocket as unknown as typeof WebSocket

    const lastOpen = () => {
      for (let i = instances.length - 1; i >= 0; i -= 1) {
        if (instances[i].readyState === OPEN) return instances[i]
      }
      return null
    }

    w.__wsControl = {
      pushLast(event: unknown) {
        lastOpen()?.onmessage?.(new MessageEvent("message", { data: JSON.stringify(event) }))
      },
      deliverRawToLast(raw: string) {
        lastOpen()?.onmessage?.(new MessageEvent("message", { data: raw }))
      },
      dropLast() {
        const target = lastOpen()
        if (target) {
          target.readyState = CLOSED
          target.onclose?.(new CloseEvent("close"))
        }
      },
    }
  })
}

async function openSettings(page: Page) {
  await page.goto("about:blank")
  await page.goto(`${baseURL}/#/`)
  await page.getByRole("button", { name: "Settings" }).click()
  await expect(page.getByRole("button", { name: "General" })).toBeVisible()
}

test.describe("Settings shell — WebSocket auto-refresh (#5 registry / #6 roles)", () => {
  test("registry_changed triggers a credentials refetch", async ({ page }) => {
    await installMockWebSocket(page)
    const state = await mockShellBackend(page)
    await openSettings(page)

    await expect.poll(() => state.registryGets).toBeGreaterThanOrEqual(1)
    const before = state.registryGets

    await page.evaluate(() => {
      ;(window as unknown as { __wsControl?: { pushLast: (e: unknown) => void } }).__wsControl?.pushLast({ type: "registry_changed" })
    })

    await expect.poll(() => state.registryGets).toBeGreaterThan(before)
  })

  test("roles_changed refetches roles once the Roles tab has loaded", async ({ page }) => {
    await installMockWebSocket(page)
    const state = await mockShellBackend(page)
    await openSettings(page)

    // Open LLM Roles so rolesData is loaded (otherwise the event is marked dirty).
    await page.getByRole("button", { name: "LLM Roles" }).click()
    await expect.poll(() => state.rolesGets).toBeGreaterThanOrEqual(1)
    const before = state.rolesGets

    await page.evaluate(() => {
      ;(window as unknown as { __wsControl?: { pushLast: (e: unknown) => void } }).__wsControl?.pushLast({ type: "roles_changed" })
    })

    await expect.poll(() => state.rolesGets).toBeGreaterThan(before)
  })

  test("#6 roles_changed refreshes app-level roles after the startup load", async ({ page }) => {
    await installMockWebSocket(page)
    const state = await mockShellBackend(page)
    await openSettings(page)

    await page.evaluate(() => {
      ;(window as unknown as { __wsControl?: { pushLast: (e: unknown) => void } }).__wsControl?.pushLast({ type: "roles_changed" })
    })

    await expect.poll(() => state.rolesGets).toBeGreaterThanOrEqual(2)
  })

  test("#5/#6 reconnect restores the subscription without refetching unchanged data", async ({ page }) => {
    await installMockWebSocket(page)
    const state = await mockShellBackend(page)
    await openSettings(page)

    await expect.poll(() => state.registryGets).toBeGreaterThanOrEqual(1)
    const before = state.registryGets

    // Drop the live socket while reconnects still succeed. Reconnect itself is
    // not evidence that config truth changed, so it must not refetch registry.
    await page.evaluate(() => {
      ;(window as unknown as { __wsControl?: { dropLast: () => void } }).__wsControl?.dropLast()
    })
    await page.waitForTimeout(1_500)
    expect(state.registryGets).toBe(before)

    await page.evaluate(() => {
      ;(window as unknown as { __wsControl?: { pushLast: (e: unknown) => void } }).__wsControl?.pushLast({ type: "registry_changed" })
    })
    await expect.poll(() => state.registryGets, { timeout: 10_000 }).toBeGreaterThan(before)
  })

  test("a malformed event is logged and does not crash the shell", async ({ page }) => {
    const consoleErrors: string[] = []
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text())
    })
    await installMockWebSocket(page)
    await mockShellBackend(page)
    await openSettings(page)

    await page.evaluate(() => {
      ;(window as unknown as { __wsControl?: { deliverRawToLast: (r: string) => void } }).__wsControl?.deliverRawToLast("{not json")
    })

    // Shell stays mounted (no white screen) and the parse failure is observable.
    await expect(page.getByRole("button", { name: "General" })).toBeVisible()
    await expect.poll(() => consoleErrors.some((line) => line.includes("parse-failed"))).toBe(true)
  })
})

test.describe("Settings shell — connection-lost warning (#5/#6)", () => {
  test("shows the warning after the reconnect backoff consistently fails, then clears on reconnect", async ({ page }) => {
    await installMockWebSocket(page)
    await mockShellBackend(page)
    await openSettings(page)

    // Initially connected → no warning.
    await expect(page.locator('[data-shell-connection-lost="true"]')).toHaveCount(0)

    // Make every future (re)connect fail, then drop the live socket.
    await page.evaluate(() => {
      ;(window as unknown as { __wsAutoOpen?: boolean }).__wsAutoOpen = false
      ;(window as unknown as { __wsControl?: { dropLast: () => void } }).__wsControl?.dropLast()
    })

    // After ≥3 consecutive failures / >10s without a connection the warning shows.
    await expect(page.locator('[data-shell-connection-lost="true"]')).toBeVisible({ timeout: 20_000 })

    // Allow reconnects to succeed again → the warning clears on the next open.
    await page.evaluate(() => {
      ;(window as unknown as { __wsAutoOpen?: boolean }).__wsAutoOpen = true
    })
    await expect(page.locator('[data-shell-connection-lost="true"]')).toHaveCount(0, { timeout: 20_000 })
  })
})
