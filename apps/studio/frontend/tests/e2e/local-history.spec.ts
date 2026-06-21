import { expect, test, type Page, type Route } from '@playwright/test'

// T-n6hist test#4 (n6-history revert) — real-DOM acceptance for the Local History
// revert flow. The gatekeeper runs this against a real machine; it route-mocks the
// backend so the assertions are deterministic. Two clauses:
//   1. Revert a selected snapshot → POST /revert with {sha} → success toast
//      'Reverted to local history snapshot'.
//   2. A GIT_REVERT_CONFLICT (409) → an error toast (never silent).
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'
const SKILL_ID = 'writer-smoke'

const snapshotSha = 'abc1234567890def'

function fulfillJson(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

function skillDetailBody() {
  return {
    manifest: {
      schema_version: '0.3.0',
      name: SKILL_ID,
      description: 'Local history revert acceptance skill',
      io: {
        inputs: { type: 'object', properties: {} },
        outputs: { type: 'object', properties: {} },
      },
      phases: ['draft', 'review'],
    },
    graph_topology: [
      { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'skill' },
      { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic' },
    ],
    node_schema_v21: {},
    io_schema: {},
    file_paths: {},
    files: {
      'GRAPH.md': '# Writer Smoke\n',
      'phases/draft/SKILL.md': '---\ntools: []\n---\nDraft phase\n',
      'phases/review/LOGIC.md': '---\nactions:\n  - validate\n---\nReview phase\n',
    },
    manifest_errors: null,
    has_golden: false,
    latest_run_metadata: null,
    lint_result: { status: 'passed', errors: [], phases_summary: [] },
  }
}

function historyBody() {
  return [
    {
      sha: snapshotSha,
      message: 'auto-run: success',
      author: 'studio-user',
      timestamp: '2026-06-18T20:00:00Z',
      kind: 'auto_run',
    },
  ]
}

async function mockBaseApi(page: Page) {
  await page.route('**/api/settings', async (route) => {
    await fulfillJson(route, {
      user_id: 'default',
      gitea_host: 'http://127.0.0.1:3000',
      default_skills_directory: '/Users/sevenx/Projects',
    })
  })
  await page.route('**/api/skills', async (route) => {
    await fulfillJson(route, [{
      id: SKILL_ID,
      name: 'Writer Smoke',
      description: 'Local history revert acceptance skill',
      phase_count: 2,
      has_golden: false,
      last_run_at: null,
      directory_path: '/Users/sevenx/Projects/writer-smoke',
    }])
  })
  await page.route(`**/api/skills/${SKILL_ID}`, async (route) => {
    await fulfillJson(route, skillDetailBody())
  })
  await page.route(`**/api/skills/${SKILL_ID}/runs`, async (route) => {
    await fulfillJson(route, { total: 0, runs: [] })
  })
  await page.route(`**/api/skills/${SKILL_ID}/golden`, async (route) => {
    await fulfillJson(route, [])
  })
  await page.route(`**/api/skills/${SKILL_ID}/history`, async (route) => {
    await fulfillJson(route, historyBody())
  })
}

function installMockWebSocket() {
  class MockWebSocket extends EventTarget {
    static CONNECTING = 0
    static OPEN = 1
    static CLOSED = 3
    readyState = MockWebSocket.CONNECTING
    onopen: ((event: Event) => void) | null = null
    onclose: ((event: Event) => void) | null = null
    constructor() {
      super()
      setTimeout(() => {
        this.readyState = MockWebSocket.OPEN
        this.onopen?.(new Event('open'))
      }, 0)
    }
    close() {
      this.readyState = MockWebSocket.CLOSED
      this.onclose?.(new Event('close'))
    }
    send() {}
  }
  Object.defineProperty(window, 'WebSocket', { value: MockWebSocket })
}

async function openLocalHistory(page: Page) {
  await page.goto(`${baseURL}/#/`)
  await page.getByText('Writer Smoke').click()
  await page.getByRole('button', { name: 'Local History' }).click()
  await expect(page.getByText('auto-run: success')).toBeVisible()
}

test.describe('Local History revert', () => {
  test('reverts the selected snapshot and toasts success', async ({ page }) => {
    test.setTimeout(20_000)
    await page.addInitScript(() => {
      window.localStorage.setItem('recentWorkspaces', '[]')
    })
    await page.addInitScript(installMockWebSocket)
    await mockBaseApi(page)

    const revertRequests: Array<{ sha?: string }> = []
    await page.route(`**/api/skills/${SKILL_ID}/revert`, async (route) => {
      revertRequests.push(route.request().postDataJSON())
      await fulfillJson(route, skillDetailBody())
    })

    await openLocalHistory(page)

    // Select then revert the snapshot.
    await page.getByText('auto-run: success').click()
    await page.getByRole('button', { name: /Revert/ }).click()

    await expect(page.getByText('Reverted to local history snapshot')).toBeVisible()
    expect(revertRequests).toEqual([{ sha: snapshotSha }])
  })

  test('surfaces a GIT_REVERT_CONFLICT as an error toast (never silent)', async ({ page }) => {
    test.setTimeout(20_000)
    await page.addInitScript(() => {
      window.localStorage.setItem('recentWorkspaces', '[]')
    })
    await page.addInitScript(installMockWebSocket)
    await mockBaseApi(page)

    await page.route(`**/api/skills/${SKILL_ID}/revert`, async (route) => {
      await fulfillJson(route, {
        code: 'GIT_REVERT_CONFLICT',
        message: 'GIT_REVERT_CONFLICT: working tree has uncommitted changes',
        details: null,
      }, 409)
    })

    await openLocalHistory(page)

    await page.getByText('auto-run: success').click()
    await page.getByRole('button', { name: /Revert/ }).click()

    await expect(page.getByText(/GIT_REVERT_CONFLICT/)).toBeVisible()
  })
})
