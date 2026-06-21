import { expect, test } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

function traceEvent(index: number) {
  return {
    schema_version: '1.0',
    event_type: index % 10 === 0 ? 'llm_call' : index % 2 === 0 ? 'phase_end' : 'phase_start',
    timestamp: `2026-05-11T00:${String(Math.floor(index / 60)).padStart(2, '0')}:${String(index % 60).padStart(2, '0')}Z`,
    phase_name: index % 2 === 0 ? 'draft' : 'review',
    input_tokens: index,
    output_tokens: index + 1,
    metadata: {
      working_memory: { index },
      tool_calls: [{ name: 'search', ok: true }],
    },
    metrics: {
      validator: { status: 'ok' },
    },
  }
}

async function mockRunApi(page: import('@playwright/test').Page) {
  const events = Array.from({ length: 1000 }, (_, index) => traceEvent(index))

  await page.route('**/api/skills/smoke', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        manifest: {
          schema_version: '2.0',
          type: 'graph',
          name: 'Smoke Skill',
          description: 'Run trace smoke skill',
          license: null,
          version: null,
          author: null,
          metadata: null,
          context_mapping: {},
          io: { inputs: [], outputs: [] },
          phases: [
            { name: 'draft', mode: 'llm', model_override: null, depends_on: undefined, prompt: null, user_prompt_template: null, agent_tools: [], steps: [], domain_protocols: [], references: [], few_shot_examples: [], context_access: ['working_memory'], llm_role: 'Agent', adopted_persona: null, max_iterations: null, max_retries: null, max_nudges: null, dead_end_threshold: null, validator: null, validator_optional: false, retry_target: null, hoist_to: null, output_schema: null, output_example: null, output_schema_md: null, output_example_md: null },
            { name: 'review', mode: 'logic', model_override: null, depends_on: 'draft', execute_steps: ['validate'], validator: null },
          ],
        },
        file_paths: {},
        has_golden: false,
        latest_run_metadata: null,
        lint_result: null,
      }),
    })
  })
  await page.route('**/api/skills/smoke/runs', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ total: 1, runs: [{ run_id: 'run-1', status: 'running', started_at: '2026-05-11T00:00:00Z', metrics: null, input_summary: null }] }),
      })
      return
    }
    await route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({ run_id: 'run-1', status: 'running', started_at: '2026-05-11T00:00:00Z', metrics: null, input_summary: null }),
    })
  })
  await page.route('**/api/skills/smoke/runs/run-1', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        metadata: { run_id: 'run-1', status: 'running', started_at: '2026-05-11T00:00:00Z', metrics: null, input_summary: null },
        input_data: {},
        events,
        final_context: null,
        artifacts: [],
      }),
    })
  })
}

test.describe('Run trace workflow smoke', () => {
  test('covers virtual trace, selection, context viewer, topology, dark mode, and disconnect UI', async ({ page }) => {
    test.setTimeout(60_000)
    await page.addInitScript(() => {
      window.sessionStorage.setItem('studio-lint-status-smoke', 'passed')
      class MockWebSocket extends EventTarget {
        static CONNECTING = 0
        static OPEN = 1
        static CLOSING = 2
        static CLOSED = 3
        readyState = MockWebSocket.CONNECTING
        onopen: ((event: Event) => void) | null = null
        onclose: ((event: Event) => void) | null = null
        onmessage: ((event: MessageEvent) => void) | null = null
        onerror: ((event: Event) => void) | null = null
        constructor() {
          super()
          setTimeout(() => {
            this.readyState = MockWebSocket.OPEN
            this.onopen?.(new Event('open'))
            setTimeout(() => {
              this.readyState = MockWebSocket.CLOSED
              this.onclose?.(new Event('close'))
            }, 50)
          }, 0)
        }
        close() {
          this.readyState = MockWebSocket.CLOSED
        }
        send() {}
      }
      Object.defineProperty(window, 'WebSocket', { value: MockWebSocket })
    })
    await mockRunApi(page)

    await page.goto(`${baseURL}/#/skill/smoke/run/run-1`)
    await expect(page.locator('[data-virtualized-count="1000"]')).toBeVisible()
    await expect(page.getByText('Run stream reconnecting')).toBeVisible()

    await page.locator('[aria-label="Trace events"]').evaluate((node) => {
      node.scrollTop = 80_000
      node.dispatchEvent(new Event('scroll'))
    })
    await expect(page.locator('[data-virtual-index]').last()).toBeVisible()

    await page.locator('[data-trace-event-id]').first().click()
    await expect(page.getByText('Micro-topology')).toBeVisible()
    await expect(page.getByText('working_memory', { exact: true })).toBeVisible()

    const viewJsonButton = page.getByRole('button', { name: /view json/i })
    await expect(viewJsonButton).toBeEnabled()
    await viewJsonButton.click({ force: true })
    await expect(page.getByText('Readonly edge context JSON')).toBeVisible()
    await page.getByRole('button', { name: /close edge context viewer/i }).click()

    await page.locator('html').evaluate((node) => node.classList.add('dark'))
    await expect(page.locator('html')).toHaveClass(/dark/)
  })

  // n5-trace atom #13 (trace-search-filter): the panel narrows the events it has
  // ALREADY received via a search box + per-phase chips, client-side (no fetch).
  // The mock streams 1000 events split evenly draft/review with 100 `llm_call`
  // rows, so each filter has a deterministic surviving count.
  test('search box and phase chip narrow the received trace events client-side', async ({ page }) => {
    test.setTimeout(60_000)
    await page.addInitScript(() => {
      window.sessionStorage.setItem('studio-lint-status-smoke', 'passed')
      class MockWebSocket extends EventTarget {
        static CONNECTING = 0
        static OPEN = 1
        static CLOSING = 2
        static CLOSED = 3
        readyState = MockWebSocket.OPEN
        onopen: ((event: Event) => void) | null = null
        onclose: ((event: Event) => void) | null = null
        onmessage: ((event: MessageEvent) => void) | null = null
        onerror: ((event: Event) => void) | null = null
        constructor() {
          super()
          setTimeout(() => {
            this.readyState = MockWebSocket.OPEN
            this.onopen?.(new Event('open'))
          }, 0)
        }
        close() {
          this.readyState = MockWebSocket.CLOSED
        }
        send() {}
      }
      Object.defineProperty(window, 'WebSocket', { value: MockWebSocket })
    })
    await mockRunApi(page)

    await page.goto(`${baseURL}/#/skill/smoke/run/run-1`)
    await expect(page.locator('[data-virtualized-count="1000"]')).toBeVisible()
    // Baseline: the whole received batch is shown.
    await expect(page.getByText('Showing 1000 of 1000 events')).toBeVisible()

    // Clause 1 — a search term shows only matching events. 100 of 1000 rows are
    // `llm_call`; the search projects in place over the received batch.
    const searchBox = page.getByPlaceholder('Search trace events')
    await searchBox.fill('llm_call')
    await expect(page.getByText('Showing 100 of 1000 events')).toBeVisible()
    await expect(page.locator('[data-virtualized-count="100"]')).toBeVisible()

    // Clearing the search restores the full received batch (no re-request).
    await searchBox.fill('')
    await expect(page.getByText('Showing 1000 of 1000 events')).toBeVisible()

    // Clause 2 — selecting a phase shows only that phase's events. 500 of 1000
    // rows are in the `review` phase.
    await page.getByRole('button', { name: 'review', exact: true }).click()
    await expect(page.getByText('Showing 500 of 1000 events')).toBeVisible()
    await expect(page.locator('[data-virtualized-count="500"]')).toBeVisible()

    // Clause 1 + 2 combine as AND on the same received batch: `review` carries no
    // `llm_call` rows (those land on even/draft indices), so the result is empty.
    await searchBox.fill('llm_call')
    await expect(page.getByText('Showing 0 of 1000 events')).toBeVisible()
  })
})
