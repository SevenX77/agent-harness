import { expect, test } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

test.describe('Eval workflow smoke', () => {
  test('loads compare, saves golden, shows publish pending, and supports dark mode', async ({ page }) => {
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
          file_paths: {},
          has_golden: true,
          latest_run_metadata: null,
          lint_result: null,
        }),
      })
    })
    await page.route('**/api/skills/smoke/runs', async (route) => {
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
          differences: [{
            field_path: 'output.answer',
            type: 'text',
            current_value: 'current value',
            golden_value: 'golden value',
            score: 0.42,
            changed: true,
          }],
          total_score: 0.42,
          golden_run_id: 'golden-run',
        }),
      })
    })
    await page.route('**/api/skills/smoke/golden', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'run-1',
          linked_input_id: 'run-1',
          created_at: '2026-05-11T00:00:00Z',
          locked: false,
          content_path: '/tmp/golden/final_state.json',
        }),
      })
    })

    await page.goto(`${baseURL}/#/skill/smoke/eval?run_id=run-1`)
    await expect(page.getByText('Current artifact')).toBeVisible()
    await expect(page.getByText('output.answer')).toBeVisible()
    await expect(page.getByText('42%')).toBeVisible()

    await page.getByRole('button', { name: /^Save as Golden$/ }).click()
    await expect(page.getByText('Saved golden baseline run-1.')).toBeVisible()

    await page.getByRole('button', { name: /^Publish$/ }).click()
    await expect(page.getByText('Publish backend pending')).toBeVisible()
    await page.getByRole('button', { name: /close publish modal/i }).click()

    await page.locator('html').evaluate((node) => node.classList.add('dark'))
    await expect(page.locator('html')).toHaveClass(/dark/)
  })
})
