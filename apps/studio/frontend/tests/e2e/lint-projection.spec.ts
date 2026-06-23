import { expect, test, type Page } from '@playwright/test'

// F-n3 (n3.1 lint near-projection): a backend/realtime lint diagnostic is projected onto THREE
// nearby surfaces so the author never hunts for the offending spot —
//   #4 canvas node badge   — `field · L<line> — message` on the phase's node (SkillNode AlertTriangle)
//   #5 Properties field     — an AlertTriangle next to the frontmatter field the engine's `field_path` named
//   #6 editor inline markers — Monaco squiggles + overview-ruler ticks at the diagnostic's line
//
// Real-machine acceptance: this drives the REAL Workspace (real GraphCanvas / PropertiesPanel /
// Monaco) in a real browser via the committed `dev-harness/lint-projection.html` entry, which mounts
// `<Workspace skillId=…>` directly. Post-#162 the home recents list is Tauri-native only, so a pure
// browser can no longer open a skill from the welcome screen — the harness is the browser-reachable
// door to the in-workspace projections. The backend is mocked at the network layer (page.route).

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'
const HARNESS = `${baseURL}/dev-harness/lint-projection.html`
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

const DRAFT_MD = [
  '---',
  'name: draft',
  'llm_role: Agent',
  'model: gpt-bogus-9000',
  'tools:',
  '  - frobnicate',
  '---',
  '',
  '# Draft phase',
  '',
  'Write the first draft.',
].join('\n')

// Realtime lint (lifted from the editor once a phase file is open): two field-bearing errors on the
// draft phase — `tools` (a field the agent Properties panel renders) and `model` (no rendered field →
// degrades to the node badge). Drives #6 (both lines marked) and #5 (Tools field marker).
const REALTIME_LINT = {
  status: 'failed',
  errors: [
    lintError({ line: 6, column: 3, error_code: 'F-v3-002', message: 'unknown tool `frobnicate`', field_path: 'tools' }),
    lintError({ line: 4, column: 8, error_code: 'F-v3-001', message: 'Unknown model alias `gpt-bogus-9000`', field_path: 'model' }),
  ],
  phases_summary: null,
}

// A single `**/*` route guarded by `pathname.startsWith('/api/')` — a broad `**/api/**` glob would
// also swallow Vite's own source modules under `src/api/…` and blank the page. Non-API requests fall
// straight through to the dev server.
async function mockLintProjectionSkill(page: Page) {
  await page.route('**/*', async (route) => {
    const pathname = new URL(route.request().url()).pathname
    if (!pathname.startsWith('/api/')) {
      await route.continue()
      return
    }
    if (pathname === `/api/skills/${SKILL_ID}/lint`) {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(REALTIME_LINT) })
      return
    }
    if (pathname === `/api/skills/${SKILL_ID}`) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
        manifest: {
          schema_version: '2.0',
          type: 'graph',
          name: 'Lint Projection Smoke',
          description: 'Lint near-projection smoke skill',
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
        file_paths: { 'phases/draft/SKILL.md': 'phases/draft/SKILL.md', 'phases/review/LOGIC.md': 'phases/review/LOGIC.md' },
        files: { 'phases/draft/SKILL.md': DRAFT_MD },
        has_golden: false,
        latest_run_metadata: null,
        // First-screen node-badge sources: lint_result flags `draft`, manifest_errors flags `review`.
        lint_result: {
          status: 'failed',
          errors: [lintError({ phase_name: 'draft', field_path: 'model', line: 12, message: 'Unknown model alias' })],
          phases_summary: null,
        },
        manifest_errors: [
          lintError({ file: 'phases/review/LOGIC.md', phase_name: 'review', field_path: 'validator', line: 4, message: 'validator must be a boolean', error_code: 'F-v3-101' }),
        ],
        }),
      })
      return
    }
    // Benign defaults for the other backend reads the workspace fires on mount; each list consumer
    // expects an array, the registry an object — wrong shapes crash render (e.g. baselines.map).
    if (pathname === '/api/llm/registry') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ endpoints: [], routes: [] }) })
      return
    }
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
}

async function openHarness(page: Page) {
  await mockLintProjectionSkill(page)
  await page.goto(`${HARNESS}?skill=${SKILL_ID}`)
  await page.waitForSelector('.react-flow__node', { timeout: 15_000 })
}

test.describe('n3.1 lint near-projection', () => {
  // Monaco renders inline `.squiggly-error` underlines only for lines laid out in the editor
  // viewport; a short viewport collapses the editor pane and the inline marks never paint (the
  // overview-ruler ticks and the lint banner still do). Pin a tall viewport so the inline-marker
  // assertion is stable.
  test.use({ viewport: { width: 1680, height: 1020 } })

  test('#4 canvas node badge — first-screen lint_result + manifest_errors paint per-node `field · L<line> — message`', async ({ page }) => {
    test.setTimeout(60_000)
    await openHarness(page)

    // `draft` carries the lint_result error; `review` carries the manifest_errors entry — both on the
    // same node channel, each with the detailed locator on the trigger (not a bare count).
    const draftBadge = page.locator('[aria-label*="model · L12 — Unknown model alias"]')
    await expect(draftBadge.first()).toBeVisible()
    await expect(draftBadge.first()).toContainText('1')

    const reviewBadge = page.locator('[aria-label*="validator · L4 — validator must be a boolean"]')
    await expect(reviewBadge.first()).toBeVisible()
  })

  test('#6 editor Monaco markers + #5 Properties field marker — realtime lint projects to the open phase file and its field', async ({ page }) => {
    test.setTimeout(60_000)
    await openHarness(page)

    const draftNode = page.locator('.react-flow__node', { hasText: 'draft' }).first()

    // Open the phase file: useDebouncedLint fires for the non-empty draft, resolving the realtime lint.
    await draftNode.dblclick()
    await page.waitForSelector('.monaco-editor', { timeout: 10_000 })

    // #6: the editor's lint banner lists BOTH flagged lines (4 = model, 6 = tools), and Monaco paints
    // inline error squiggles for them (setModelMarkers, owner `studio-lint`).
    await expect(page.locator('.monaco-editor').first()).toBeVisible()
    await expect(page.getByText('unknown tool `frobnicate`')).toBeVisible()
    await expect(page.getByText('Unknown model alias `gpt-bogus-9000`')).toBeVisible()
    const squiggles = page.locator('.monaco-editor .squiggly-error')
    await expect.poll(async () => squiggles.count(), { timeout: 10_000 }).toBeGreaterThanOrEqual(1)

    // #5: with the realtime lint resolved, selecting the draft node marks the `tools` frontmatter
    // field (the `model` error has no rendered field on an agent node → stays on the node badge).
    await draftNode.click()
    const fieldMarker = page.locator('[aria-label^="Field has"]')
    await expect(fieldMarker.first()).toBeVisible()
    await expect(fieldMarker.first()).toHaveAttribute('aria-label', /unknown tool `frobnicate`/)
  })
})
