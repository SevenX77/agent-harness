import { expect, test, type Page } from '@playwright/test'

// F-n3 (n3-lint atom #4, canvas-node-projection): the canvas node error badge is fed from THREE
// parallel sources — first-screen SkillDetail.lint_result + SkillDetail.manifest_errors seed the
// initial projection, and the editor's realtime lint overlays it. This spec covers the first-screen
// path real-machine: opening a skill whose backend lint flagged a phase shows that phase's node
// badge with the per-error `field · L<line> — message` detail (not just a bare count).
//
// Real-machine acceptance: the gatekeeper runs this with the dev server + real navigation.

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

const SKILL_ID = 'lint-projection-smoke'

function lintError(overrides: Record<string, unknown> = {}) {
  return {
    file: 'phases/draft/SKILL.md',
    line: 12,
    column: null,
    error_code: 'F-v3-001',
    severity: 'error',
    message: 'Unknown model alias',
    phase_name: 'draft',
    field_path: 'model',
    source_path: null,
    ...overrides,
  }
}

async function mockLintProjectionSkill(page: Page) {
  await page.route('**/api/skills', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify([{
        id: SKILL_ID,
        name: 'Lint Projection Smoke',
        description: 'Canvas node lint projection smoke skill',
        phase_count: 2,
        has_golden: false,
        last_run_at: null,
        directory_path: null,
      }]),
    })
  })

  await page.route(`**/api/skills/${SKILL_ID}`, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        manifest: {
          schema_version: '2.0',
          type: 'graph',
          name: 'Lint Projection Smoke',
          description: 'Canvas node lint projection smoke skill',
          license: null,
          version: null,
          author: null,
          metadata: null,
          context_mapping: {},
          io: { inputs: [], outputs: [] },
          phases: [
            { name: 'draft', mode: 'llm', model_override: null, depends_on: undefined, prompt: 'Draft', user_prompt_template: null, agent_tools: [], steps: [], domain_protocols: [], references: [], few_shot_examples: [], context_access: ['working_memory'], llm_role: 'Agent', adopted_persona: null, max_iterations: null, max_retries: null, max_nudges: null, dead_end_threshold: null, validator: null, validator_optional: false, retry_target: null, hoist_to: null, output_schema: null, output_example: null, output_schema_md: null, output_example_md: null },
            { name: 'review', mode: 'logic', model_override: null, depends_on: 'draft', execute_steps: ['validate'], validator: null },
          ],
        },
        file_paths: {},
        has_golden: false,
        latest_run_metadata: null,
        // First-screen sources for the node projection: lint_result flags `draft`, manifest_errors
        // flags `review`. Both must paint their node badge before any editor lint runs.
        lint_result: {
          status: 'failed',
          errors: [lintError({ file: 'phases/draft/SKILL.md', phase_name: 'draft', field_path: 'model', line: 12, message: 'Unknown model alias' })],
          phases_summary: null,
        },
        manifest_errors: [
          lintError({ file: 'phases/review/LOGIC.md', phase_name: 'review', field_path: 'validator', line: 4, message: 'validator must be a boolean', error_code: 'F-v3-101' }),
        ],
      }),
    })
  })
}

test.describe('Canvas node lint projection (F-n3 atom #4)', () => {
  test('first-screen lint_result + manifest_errors paint per-node error badges with field · L<line> — message', async ({ page }) => {
    test.setTimeout(60_000)
    await page.addInitScript((skillId) => {
      window.sessionStorage.setItem(`studio-lint-status-${skillId}`, 'failed')
    }, SKILL_ID)
    await mockLintProjectionSkill(page)

    await page.goto(baseURL)
    await page.getByRole('button', { name: /Lint Projection Smoke/ }).first().click()

    // The `draft` node carries the lint_result error: badge + detailed locator on the trigger.
    const draftBadge = page.locator('[aria-label*="model · L12 — Unknown model alias"]')
    await expect(draftBadge.first()).toBeVisible()
    await expect(draftBadge.first()).toContainText('1')

    // The `review` node carries the manifest_errors entry — projected on the same channel.
    const reviewBadge = page.locator('[aria-label*="validator · L4 — validator must be a boolean"]')
    await expect(reviewBadge.first()).toBeVisible()
  })
})
