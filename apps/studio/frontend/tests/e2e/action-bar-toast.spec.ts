import { expect, test, type Page, type Route } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'
const SKILL_ID = 'writer-smoke'

const artifactRef = {
  artifact_id: SKILL_ID,
  content_hash: 'sha256:wave3contenthash',
  store: 'ephemeral',
  version: null,
  manifest_ref: `${SKILL_ID}/manifest.json`,
  source_map_ref: `${SKILL_ID}/source-map.json`,
  execution_fingerprint: 'sha256:wave3fingerprint',
}

function runMetadata(runId: string, status: 'running' | 'success' = 'running') {
  return {
    run_id: runId,
    status,
    started_at: '2026-06-18T20:00:00Z',
    metrics: null,
    input_summary: '{}',
    artifact_ref: artifactRef,
    source_map_ref: artifactRef.source_map_ref,
    execution_fingerprint: artifactRef.execution_fingerprint,
  }
}

function fulfillJson(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function mockWorkspaceApi(page: Page, runRequests: unknown[]) {
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
      description: 'Wave3 browser validation skill',
      phase_count: 2,
      has_golden: false,
      last_run_at: null,
      directory_path: '/Users/sevenx/Projects/writer-smoke',
    }])
  })
  await page.route(`**/api/skills/${SKILL_ID}`, async (route) => {
    await fulfillJson(route, {
      manifest: {
        schema_version: '0.3.0',
        name: SKILL_ID,
        description: 'Wave3 browser validation skill',
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
    })
  })
  await page.route(`**/api/skills/${SKILL_ID}/compile`, async (route) => {
    await fulfillJson(route, {
      skill_id: SKILL_ID,
      status: 'ok',
      phase_count: 2,
      manifest_name: SKILL_ID,
      artifact_ref: artifactRef,
      source_map_ref: artifactRef.source_map_ref,
      execution_fingerprint: artifactRef.execution_fingerprint,
    })
  })
  await page.route(`**/api/skills/${SKILL_ID}/runs/predict`, async (route) => {
    await fulfillJson(route, {
      run_id: 'predict-run-1',
      status: 'success',
      metadata: runMetadata('predict-run-1', 'success'),
    })
  })
  await page.route(`**/api/skills/${SKILL_ID}/runs`, async (route) => {
    if (route.request().method() === 'POST') {
      runRequests.push(route.request().postDataJSON())
      await fulfillJson(route, runMetadata('run-1'), 202)
      return
    }
    await fulfillJson(route, { total: 0, runs: [] })
  })
}

test.describe('Studio action bar', () => {
  test('success toasts do not block the next action at narrow desktop width', async ({ page }) => {
    test.setTimeout(20_000)
    await page.setViewportSize({ width: 768, height: 900 })
    await page.addInitScript(() => {
      window.localStorage.setItem('recentWorkspaces', '[]')
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
    })
    const runRequests: unknown[] = []
    await mockWorkspaceApi(page, runRequests)

    await page.goto(`${baseURL}/#/`)
    await page.getByText('Writer Smoke').click()
    await expect(page.locator('.react-flow__node').filter({ hasText: 'review' })).toBeVisible()

    await page.getByRole('button', { name: 'Compile' }).click()
    await expect(page.getByRole('button', { name: 'Predict' })).toBeEnabled()
    await page.getByRole('button', { name: 'Predict' }).click()
    await expect(page.getByRole('button', { name: 'Run' })).toBeEnabled()
    await page.getByRole('button', { name: 'Run' }).click()

    await expect.poll(() => runRequests.length).toBe(1)
  })
})
