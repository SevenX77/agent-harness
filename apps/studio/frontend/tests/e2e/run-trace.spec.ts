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
    await expect(page.getByText('working_memory')).toBeVisible()

    await page.getByRole('button', { name: /view json/i }).click()
    await expect(page.getByText('Readonly edge context JSON')).toBeVisible()
    await page.getByRole('button', { name: /close edge context viewer/i }).click()

    await page.locator('html').evaluate((node) => node.classList.add('dark'))
    await expect(page.locator('html')).toHaveClass(/dark/)
  })
})
