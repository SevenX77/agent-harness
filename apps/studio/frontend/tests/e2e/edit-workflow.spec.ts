import { expect, test } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

test.describe('Edit workflow smoke', () => {
  test('covers graph, lint guard, Monaco lazy, schema inference, subgraph expand, and dark mode', async ({ page }) => {
    let lintCount = 0

    await page.route('**/api/skills', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify([{
          id: 'smoke',
          name: 'Smoke Skill',
          description: 'Playwright smoke skill',
          phase_count: 2,
          has_golden: false,
          last_run_at: null,
        }]),
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
            description: 'Playwright smoke skill',
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
                mode: 'logic',
                model_override: null,
                depends_on: 'draft',
                subgraph: './review.md',
                execute_steps: ['Check summary'],
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

    await page.route('**/api/skills/smoke/lint', async (route) => {
      lintCount += 1
      const failed = lintCount > 1
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          status: failed ? 'failed' : 'passed',
          errors: failed ? [{ line: 1, column: 1, error_code: 'SMOKE', severity: 'error', message: 'Smoke failure', phase_name: 'draft' }] : [],
          phases_summary: [],
        }),
      })
    })

    await page.goto(`${baseURL}/#/skill/smoke/edit`)
    await expect(page.getByText('Edit graph')).toBeVisible()
    await expect(page.getByTestId('rf__node-draft').getByText('draft', { exact: true })).toBeVisible()
    await expect(page.locator('.react-flow__edge')).toHaveCount(1)

    await page.getByTestId('rf__node-review').getByText('review', { exact: true }).click()
    await page.getByRole('button', { name: /expand subgraph/i }).click()
    await expect(page.getByRole('definition').filter({ hasText: './review.md' })).toBeVisible()

    await page.getByLabel('JSON input for schema inference').fill('{"topic":"demo","count":2,"ok":true}')
    await expect(page.getByText('"type": "object"')).toBeVisible()

    await expect(page.getByText('Agent prompt', { exact: true })).toBeVisible()
    await page.locator('html').evaluate((node) => node.classList.add('dark'))
    await expect(page.locator('html')).toHaveClass(/dark/)

    await expect(page.getByText('Compile guard: Passed')).toBeVisible({ timeout: 3000 })
    await page.locator('.monaco-editor .view-line').first().click()
    await page.keyboard.type(' fail')
    await expect(page.getByText('Compile guard: Failed')).toBeVisible({ timeout: 3000 })
    await expect(page.getByLabel('Predict')).toHaveAttribute('aria-disabled', 'true')
    await expect(page.getByLabel('Run')).toHaveAttribute('aria-disabled', 'true')
  })
})
