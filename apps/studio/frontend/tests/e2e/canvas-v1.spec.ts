import { expect, test, type Page } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

async function mockCanvasSkill(page: Page) {
  await page.route('**/api/skills', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify([{
        id: 'canvas-v1-smoke',
        name: 'Canvas V1 Smoke',
        description: 'Canvas v1 smoke skill',
        phase_count: 3,
        has_golden: false,
        last_run_at: null,
        directory_path: null,
      }]),
    })
  })

  await page.route('**/api/skills/canvas-v1-smoke', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        manifest: {
          schema_version: '2.0',
          type: 'graph',
          name: 'Canvas V1 Smoke',
          description: 'Canvas v1 smoke skill',
          license: null,
          version: null,
          author: null,
          metadata: null,
          context_mapping: {},
          io: {
            inputs: [{ name: 'topic', source: 'runtime', type: 'string', default: null }],
            outputs: [{ name: 'summary', target: 'artifact', type: 'string', path: null }],
          },
          phases: [
            {
              name: 'draft',
              mode: 'llm',
              model_override: null,
              prompt: 'Draft',
              user_prompt_template: null,
              agent_tools: [],
              steps: [],
              domain_protocols: [],
              references: [],
              few_shot_examples: [],
              context_access: ['working_memory'],
              llm_role: 'Agent',
              adopted_persona: null,
              max_iterations: null,
              max_retries: null,
              max_nudges: null,
              dead_end_threshold: null,
              validator: null,
              validator_optional: false,
              retry_target: null,
              hoist_to: null,
              output_schema: null,
              output_example: null,
              output_schema_md: null,
              output_example_md: null,
            },
            {
              name: 'review',
              mode: 'llm',
              model_override: null,
              depends_on: 'draft',
              subgraph: './review.md',
              prompt: 'Review',
              user_prompt_template: null,
              agent_tools: [],
              steps: [],
              domain_protocols: [],
              references: [],
              few_shot_examples: [],
              context_access: ['working_memory'],
              llm_role: 'Reviewer',
              adopted_persona: null,
              max_iterations: null,
              max_retries: null,
              max_nudges: null,
              dead_end_threshold: null,
              validator: null,
              validator_optional: false,
              retry_target: null,
              hoist_to: null,
              output_schema: null,
              output_example: null,
              output_schema_md: null,
              output_example_md: null,
            },
            {
              name: 'finalize',
              mode: 'logic',
              model_override: null,
              depends_on: 'review',
              execute_steps: ['Finalize summary'],
              validator: null,
            },
          ],
        },
        file_paths: {},
        has_golden: false,
        latest_run_metadata: null,
        lint_result: null,
      }),
    })
  })
}

async function openCanvasSkill(page: Page) {
    await page.goto(baseURL)
    await expect(page.getByText('Canvas V1 Smoke').first()).toBeVisible()
    await page.getByRole('button', { name: /Canvas V1 Smoke/ }).first().click()
}

test.describe('Canvas v1 design-time visual', () => {
  test('captures desktop initial and expanded canvas states', async ({ page }) => {
    await mockCanvasSkill(page)
    await openCanvasSkill(page)

    await expect(page.getByText('Edit graph')).toHaveCount(0)
    await expect(page.getByText('Input', { exact: true })).toBeVisible()
    await expect(page.getByText('Output', { exact: true })).toBeVisible()
    await expect(page.getByText('topic', { exact: true })).toBeVisible()
    await expect(page.getByText('summary', { exact: true })).toBeVisible()

    await expect(page.locator('.react-flow__edge-path[marker-end]')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '查看连线传递数据' }).first()).toBeVisible()

    await page.screenshot({ path: 'test-results/canvas-v1-desktop-initial.png', fullPage: false })

    await expect(page.getByRole('button', { name: '展开子图' })).toBeVisible()
    await page.getByRole('button', { name: '展开子图' }).click()
    await expect(page.getByRole('button', { name: '收起子图' })).toBeVisible()
    await expect(page.getByText('./review.md')).toBeVisible()

    await page.screenshot({ path: 'test-results/canvas-v1-desktop-expanded.png', fullPage: false })
  })

  test('captures narrow canvas state', async ({ page }) => {
    await page.setViewportSize({ width: 480, height: 800 })
    await mockCanvasSkill(page)
    await openCanvasSkill(page)

    await expect(page.getByText('Input', { exact: true })).toBeVisible()
    await expect(page.getByText('Output', { exact: true })).toBeVisible()

    await page.screenshot({ path: 'test-results/canvas-v1-narrow.png', fullPage: false })
  })
})
