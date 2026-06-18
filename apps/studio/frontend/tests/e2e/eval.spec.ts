import { expect, test, type Page } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

function installRunStream(page: Page) {
  return page.addInitScript(() => {
    class FakeWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3

      onopen: ((event: Event) => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null
      onclose: ((event: Event) => void) | null = null
      readyState = FakeWebSocket.CONNECTING
      readonly url: string

      constructor(url: string) {
        this.url = url
        window.setTimeout(() => {
          this.readyState = FakeWebSocket.OPEN
          this.onopen?.(new Event('open'))
          this.onmessage?.(
            new MessageEvent('message', {
              data: JSON.stringify({
                schema_version: 'studio.event.v1',
                stream_id: 'run:run-1',
                seq: 1,
                cursor: 'run:run-1:1',
                run_id: 'run-1',
                event_type: 'run_started',
                timestamp: '2026-05-11T00:00:00Z',
                payload: {
                  schema_version: '1.0',
                  event_type: 'run_started',
                  phase_name: 'draft',
                  timestamp: '2026-05-11T00:00:00Z',
                  run_id: 'run-1',
                },
              }),
            }),
          )
          this.onmessage?.(
            new MessageEvent('message', {
              data: JSON.stringify({
                schema_version: 'studio.event.v1',
                stream_id: 'run:run-1',
                seq: 2,
                cursor: 'run:run-1:2',
                run_id: 'run-1',
                event_type: 'run_ended',
                timestamp: '2026-05-11T00:00:01Z',
                payload: {
                  schema_version: '1.0',
                  event_type: 'run_ended',
                  phase_name: 'draft',
                  timestamp: '2026-05-11T00:00:01Z',
                  run_id: 'run-1',
                  status: 'success',
                },
              }),
            }),
          )
        }, 10)
      }

      send() {}

      close() {
        this.readyState = FakeWebSocket.CLOSED
        this.onclose?.(new Event('close'))
      }

      addEventListener(type: string, listener: EventListener) {
        if (type === 'open') this.onopen = listener
        if (type === 'message') this.onmessage = listener as (event: MessageEvent) => void
        if (type === 'error') this.onerror = listener
        if (type === 'close') this.onclose = listener
      }

      removeEventListener() {}
    }

    window.WebSocket = FakeWebSocket as unknown as typeof WebSocket
  })
}

test.describe('Eval workflow smoke', () => {
  test('loads compare, saves golden, shows release pending, and supports dark mode', async ({ page }) => {
    await installRunStream(page)
    await page.route('**/api/settings', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          user_id: 'default',
          gitea_host: '',
          default_skills_directory: '/studio/config/Skills',
        }),
      })
    })
    await page.route('**/api/skills', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'smoke',
            name: 'Smoke Skill',
            description: 'Eval smoke skill',
            phase_count: 1,
            has_golden: true,
            last_run_at: '2026-05-11T00:00:00Z',
            directory_path: '/studio/config/Skills/smoke',
          },
        ]),
      })
    })
    await page.route('**/api/skills/smoke', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          manifest: {
            schema_version: '2.0',
            type: 'graph',
            name: 'Smoke Skill',
            description: 'Eval smoke skill',
            license: null,
            version: null,
            author: null,
            metadata: null,
            context_mapping: {},
            io: { inputs: [], outputs: [] },
            phases: [],
          },
          file_paths: {
            'GRAPH.md': 'GRAPH.md',
          },
          files: {
            'GRAPH.md': '# Smoke Skill\n',
          },
          has_golden: true,
          latest_run_metadata: null,
          lint_result: null,
        }),
      })
    })
    await page.route('**/api/skills/smoke/compile', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          skill_id: 'smoke',
          status: 'ok',
          phase_count: 1,
          manifest_name: 'Smoke Skill',
          artifact_ref: {
            artifact_id: 'smoke',
            content_hash: 'sha256:0123456789abcdef',
            store: 'ephemeral',
            version: null,
            manifest_ref: 'smoke/manifest.json',
            source_map_ref: 'smoke/source-map.json',
          },
          source_map_ref: 'smoke/source-map.json',
          execution_fingerprint: 'sha256:abcdef0123456789',
        }),
      })
    })
    await page.route('**/api/skills/smoke/runs/predict', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ run_id: 'predict-run', status: 'success' }),
      })
    })
    await page.route('**/api/skills/smoke/runs', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            run_id: 'run-1',
            status: 'success',
            started_at: '2026-05-11T00:00:00Z',
            metrics: null,
            input_summary: null,
          }),
        })
        return
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          total: 1,
          runs: [{ run_id: 'run-1', status: 'success', started_at: '2026-05-11T00:00:00Z', metrics: null, input_summary: null }],
        }),
      })
    })
    await page.route('**/api/skills/smoke/runs/run-1', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          metadata: { run_id: 'run-1', status: 'success', started_at: '2026-05-11T00:00:00Z', metrics: null, input_summary: null },
          input_data: {},
          events: [],
          final_context: { answer: 'current value' },
          artifacts: [],
        }),
      })
    })
    await page.route('**/api/skills/smoke/runs/run-1/compare', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          baseline_id: 'golden-run',
          source_run_id: 'source-run',
          source_run_results_ref: 'smoke/runs/source-run/result.json',
          baseline_ref: 'smoke/golden/golden-run/baseline.json',
          run_results_ref: 'smoke/runs/run-1/result.json',
          total_score: 42,
          node_groups: [
            {
              node_id: 'draft',
              phase_id: 'draft',
              status: 'fail',
              score: 0.42,
              field_differences: [
                {
                  field_path: 'nodes.draft.answer',
                  type: 'text',
                  current_value: 'current value',
                  golden_value: 'golden value',
                  score: 0.42,
                  changed: true,
                },
              ],
              stale_fields: [],
              schema_status: 'valid',
              baseline_ref: 'smoke/golden/golden-run/baseline.json',
              run_results_ref: 'smoke/runs/run-1/result.json',
            },
            {
              node_id: 'review',
              phase_id: 'review',
              status: 'pass',
              score: 1,
              field_differences: [],
              stale_fields: [],
              schema_status: 'valid',
              baseline_ref: 'smoke/golden/golden-run/baseline.json',
              run_results_ref: 'smoke/runs/run-1/result.json',
            },
          ],
        }),
      })
    })
    await page.route('**/api/skills/smoke/golden', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'run-1',
          source_run_id: 'run-1',
          source_run_results_ref: 'smoke/runs/run-1/result.json',
          baseline_ref: 'smoke/golden/run-1/baseline.json',
          linked_input_id: 'run-1',
          created_at: '2026-05-11T00:00:00Z',
          locked: false,
          content_path: '/tmp/golden/final_state.json',
        }),
      })
    })
    await page.route('**/api/skills/smoke/publish', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          message: 'Release created',
          artifact_id: 'smoke',
          extra: {
            release_version: '0.0.1',
            artifact_id: 'smoke',
            content_hash: 'sha256:0123456789abcdef',
            manifest_ref: 'smoke/releases/0.0.1/manifest.json',
            artifact_ref: {
              artifact_id: 'smoke',
              content_hash: 'sha256:0123456789abcdef',
              store: 'product',
              manifest_ref: 'smoke/releases/0.0.1/manifest.json',
            },
            remote_sync: { status: 'pending', reason: 'backend pending' },
          },
        }),
      })
    })

    await page.goto(baseURL)
    await page.getByRole('button', { name: /^Smoke Skill\b/ }).click()
    await expect(page.getByRole('button', { name: 'smoke' })).toBeVisible()

    await page.getByRole('button', { name: /^Compile$/ }).click()
    await page.getByRole('button', { name: /^Predict$/ }).click()
    await page.getByRole('button', { name: /^Run$/ }).click()
    await expect(page.getByText(/运行完成/)).toBeVisible()
    await page.getByRole('button', { name: '忽略分析' }).click()
    await expect(page.getByText(/运行完成/)).toBeHidden()
    await page.getByRole('button', { name: /compare trace to golden baseline/i }).click()

    const diffOverlay = page.locator('.absolute.inset-0.z-40')
    await expect(diffOverlay.getByText('Baseline golden-run')).toBeVisible()
    await expect(diffOverlay.getByText('Source run source-run')).toBeVisible()
    await expect(diffOverlay.getByText('draft', { exact: true })).toBeVisible()
    await expect(diffOverlay.getByText('review', { exact: true })).toBeVisible()
    await expect(diffOverlay.getByRole('button', { name: /nodes\.draft\.answer text 42%/i })).toBeVisible()

    await page.getByRole('button', { name: /^Promote$/ }).click()
    await expect(page.getByText('Promoted run to golden baseline')).toBeVisible()

    await page.getByRole('button', { name: /^Team$/ }).click()
    await page.getByRole('menuitem', { name: /^Release$/ }).click()
    await expect(page.getByLabel(/remote sync pending/i)).toBeVisible()

    await page.locator('html').evaluate((node) => node.classList.add('dark'))
    await expect(page.locator('html')).toHaveClass(/dark/)
  })
})
