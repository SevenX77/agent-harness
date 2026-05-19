import { expect, test } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

test.describe('Tauri desktop integration smoke', () => {
  test('keeps hash route stable on refresh and exposes desktop IDE buttons', async ({ page }) => {
    await page.route('**/api/skills/smoke', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          manifest: {
            schema_version: '2.0',
            type: 'graph',
            name: 'Smoke Skill',
            description: 'Tauri smoke skill',
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
            ],
          },
          file_paths: {},
          has_golden: false,
          latest_run_metadata: null,
          lint_result: null,
        }),
      })
    })
    await page.route('**/api/copilot/credentials', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          active_backend: 'claude',
          backends: {
            claude: { has_key: false },
            deepseek: { has_key: false },
            gemini: { has_key: false, V1_5_PLACEHOLDER: true },
            openai: { has_key: false, V1_5_PLACEHOLDER: true },
          },
        }),
      })
    })

    await page.goto(`${baseURL}/#/skill/smoke/edit`)
    await expect(page.getByText('Edit graph')).toBeVisible()
    await page.reload()
    await expect(page.getByText('Edit graph')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Open in Cursor' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Open in Terminal' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Open in Codex' })).toBeVisible()

    await page.getByRole('button', { name: 'Open in Cursor' }).click()
    await expect(page.getByText('桌面端 only')).toBeVisible()
  })
})
