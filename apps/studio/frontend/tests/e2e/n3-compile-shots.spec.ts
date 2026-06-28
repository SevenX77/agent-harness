import { expect, test, type Page } from '@playwright/test'

// Real-machine screenshot capture for the N3 Compile node — the bottom Compile
// error drawer (n3_drawer slice) and the center action-bar build-stage gating
// (n3_gating slice). Drives the REAL Workspace state machine (compileSkillById /
// handlePredict / deriveBuildStage / CompileErrorDrawer / center-action-bar)
// through the committed `dev-harness/lint-projection.html` entry, which mounts
// `<Workspace skillId=…>` directly (post-#162 the home recents list is Tauri-
// native only, so this harness is the browser-reachable door to in-workspace UI).
// The backend is mocked at the network layer (page.route). Each test saves a PNG
// into test-results/ for curation into the handbook screenshots dir.
//
// Driving contract (read from Workspace.tsx + center-action-bar.tsx):
//   POST /skills/:id/compile  -> 200 {status:'ok',...}           => stage compile-pass (Predict lights)
//                             -> 422 {code:'compile_failed',...} => stage compile-fail + drawer auto-opens
//   POST /skills/:id/runs/predict -> {status:'success'}          => stage predict-pass (Run lights)
//   sessionStorage studio-lint-status-<id>='passed'              => deriveBuildStage falls back to compile-pass
//   disabled Predict/Run wrapped in LockableButton               => hover shows the lock-reason Tooltip

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'
const HARNESS = `${baseURL}/dev-harness/lint-projection.html`
const SKILL_ID = 'n3-compile-demo'

const DRAFT_MD = ['---', 'name: draft', 'llm_role: Agent', 'model: gpt-4o', '---', '', '# Draft phase', '', 'Write the first draft.'].join('\n')

// CompileFailure.errors → the drawer lists each as `file:line - field - message`.
const COMPILE_ERRORS = [
  { file: 'phases/review/LOGIC.md', line: 4, field: 'io.outputs.summary', severity: 'fatal', message: 'Output field `summary` is never produced by any phase' },
  { file: 'phases/draft/SKILL.md', line: 7, field: 'exit_contract', severity: 'fatal', message: 'exit_contract must call finish_task' },
  { file: 'GRAPH.md', line: 3, field: 'phases', severity: 'warning', message: 'Phase `review` declares an input no upstream phase supplies' },
]

const COMPILE_OK = {
  skill_id: SKILL_ID, status: 'ok', phase_count: 2, manifest_name: 'N3 Compile Demo',
  artifact_ref: { artifact_id: 'art-1', content_hash: `sha256:${'0'.repeat(8)}`, store: 'ephemeral', version: null, manifest_ref: 'm1', source_map_ref: 's1', execution_fingerprint: 'fp00000000' },
  source_map_ref: 's1', execution_fingerprint: 'fp00000000',
}

type CompileMode = 'pass' | 'fail'

// A single `**/*` route guarded by `pathname.startsWith('/api/')` — a broad `**/api/**`
// glob would also swallow Vite's own `/src/api/…` modules and blank the page.
async function mock(page: Page, compileMode: CompileMode) {
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url())
    const pathname = url.pathname
    if (!pathname.startsWith('/api/')) {
      await route.continue()
      return
    }
    if (pathname === `/api/skills/${SKILL_ID}/compile`) {
      if (compileMode === 'fail') {
        await route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ code: 'compile_failed', detail: `${COMPILE_ERRORS.length} compile errors`, errors: COMPILE_ERRORS }) })
      } else {
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(COMPILE_OK) })
      }
      return
    }
    if (pathname === `/api/skills/${SKILL_ID}/runs/predict`) {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ is_predict: true, status: 'success', phases: [], path_diff: null }) })
      return
    }
    if (pathname === `/api/skills/${SKILL_ID}`) {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({
        manifest: {
          schema_version: '2.0', type: 'graph', name: 'N3 Compile Demo', description: 'Compile node demo',
          license: null, version: null, author: null, metadata: null, context_mapping: {},
          io: { inputs: [], outputs: [] },
          phases: [
            { name: 'draft', mode: 'llm', model_override: null, depends_on: undefined, prompt: 'Draft', user_prompt_template: null, agent_tools: [], steps: [], domain_protocols: [], references: [], few_shot_examples: [], context_access: ['working_memory'], llm_role: 'Agent', adopted_persona: null, max_iterations: null, max_retries: null, max_nudges: null, dead_end_threshold: null, validator: null, validator_optional: false, retry_target: null, hoist_to: null, output_schema: null, output_example: null, output_schema_md: null, output_example_md: null },
            { name: 'review', mode: 'logic', model_override: null, depends_on: 'draft', execute_steps: ['validate'], validator: null },
          ],
        },
        file_paths: { 'phases/draft/SKILL.md': 'phases/draft/SKILL.md', 'phases/review/LOGIC.md': 'phases/review/LOGIC.md' },
        files: { 'phases/draft/SKILL.md': DRAFT_MD },
        has_golden: false, latest_run_metadata: null, lint_result: null, manifest_errors: null,
      }) })
      return
    }
    if (pathname === '/api/llm/registry') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ endpoints: [], routes: [] }) })
      return
    }
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
}

// Scope to the canvas (the action bar lives there) + exact names — a bare
// name:'Compile' also matches the breadcrumb button "n3-compile-demo".
const canvas = (page: Page) => page.getByTestId('canvas')
const compileBtn = (page: Page) => canvas(page).getByRole('button', { name: 'Compile', exact: true })
const predictBtn = (page: Page) => canvas(page).getByRole('button', { name: 'Predict', exact: true })
const runBtn = (page: Page) => canvas(page).getByRole('button', { name: 'Run', exact: true })

// Dismiss the right-hand Copilot's retry toasts so they don't overlay the bar.
async function clearToasts(page: Page) {
  for (const x of await page.locator('[data-sonner-toast] button[aria-label]').all()) await x.click().catch(() => {})
}

async function open(page: Page, compileMode: CompileMode = 'pass', lintPassed = false) {
  await mock(page, compileMode)
  if (lintPassed) {
    await page.addInitScript((id) => window.sessionStorage.setItem(`studio-lint-status-${id}`, 'passed'), SKILL_ID)
  }
  await page.goto(`${HARNESS}?skill=${SKILL_ID}`)
  await page.waitForSelector('.react-flow__node', { timeout: 15_000 })
  await expect(compileBtn(page)).toBeVisible({ timeout: 10_000 })
  await page.waitForTimeout(400)
}

test.use({ viewport: { width: 1440, height: 900 } })

test.describe('N3 compile drawer + action-bar gating real-machine screenshots', () => {
  // ── n3_drawer slice ──────────────────────────────────────────────────────
  test('drawer: compile-fail auto-opens the bottom error drawer (#7 fail · #8 · #9)', async ({ page }) => {
    await open(page, 'fail')
    await compileBtn(page).click()
    const drawer = page.locator('[data-slot="compile-drawer-content"]')
    await expect(drawer).toBeVisible({ timeout: 10_000 })
    await expect(drawer.getByText('3 compile errors')).toBeVisible()
    await expect(drawer.getByRole('button', { name: 'Copy all compile errors' })).toBeVisible()
    await expect(drawer.getByText('phases/review/LOGIC.md:4 - io.outputs.summary - Output field `summary` is never produced by any phase')).toBeVisible()
    // #9: drawer is modal=false + canvas-scoped → the canvas/sidebars stay reachable
    // (no old viewport-blanketing floating panel).
    await clearToasts(page)
    await page.waitForTimeout(300)
    await page.screenshot({ path: 'test-results/n3-drawer-01-fail-drawer.png' })
  })

  test('drawer: compile-pass closes the drawer and lights Predict (#7 success path)', async ({ page }) => {
    await open(page, 'pass')
    await compileBtn(page).click()
    await expect(predictBtn(page)).toBeEnabled({ timeout: 10_000 })
    await expect(page.locator('[data-slot="compile-drawer-content"]')).toHaveCount(0)
    await clearToasts(page)
    await page.waitForTimeout(300)
    await page.screenshot({ path: 'test-results/n3-drawer-02-compile-pass.png' })
  })

  // ── n3_gating slice ──────────────────────────────────────────────────────
  test('gating: idle gates Predict/Run, highlights Compile (#10 · #11)', async ({ page }) => {
    await open(page, 'pass')
    await expect(predictBtn(page)).toBeDisabled()
    await expect(runBtn(page)).toBeDisabled()
    await expect(compileBtn(page)).toBeEnabled()
    await clearToasts(page)
    await page.screenshot({ path: 'test-results/n3-gating-01-gated.png' })
  })

  test('gating: compile-pass lights Predict, Run still gated (#11 · #14)', async ({ page }) => {
    await open(page, 'pass')
    await compileBtn(page).click()
    await expect(predictBtn(page)).toBeEnabled({ timeout: 10_000 })
    await expect(runBtn(page)).toBeDisabled()
    await clearToasts(page)
    await page.waitForTimeout(300)
    await page.screenshot({ path: 'test-results/n3-gating-02-predict-lit.png' })
  })

  test('gating: predict-pass unlocks Run (#14)', async ({ page }) => {
    await open(page, 'pass')
    await compileBtn(page).click()
    await expect(predictBtn(page)).toBeEnabled({ timeout: 10_000 })
    await predictBtn(page).click()
    await expect(runBtn(page)).toBeEnabled({ timeout: 10_000 })
    await clearToasts(page)
    await page.waitForTimeout(300)
    await page.screenshot({ path: 'test-results/n3-gating-03-run-lit.png' })
  })

  test('gating: a passed editor lint auto-lights Predict without a manual Compile (#12)', async ({ page }) => {
    await open(page, 'pass', /* lintPassed */ true)
    // No Compile click: deriveBuildStage falls back to the passed lint => compile-pass.
    await expect(predictBtn(page)).toBeEnabled({ timeout: 10_000 })
    await expect(runBtn(page)).toBeDisabled()
    await clearToasts(page)
    await page.screenshot({ path: 'test-results/n3-gating-04-lint-drives.png' })
  })

  test('gating: hovering the locked Predict shows its lock reason (#13)', async ({ page }) => {
    await open(page, 'pass')
    await clearToasts(page)
    // The disabled button swallows pointer events, so hover its LockableButton
    // wrapper span (aria-label carries the reason).
    await page.locator('span[aria-label="Compile must pass first"]').hover()
    await expect(page.getByRole('tooltip').getByText('Compile must pass first')).toBeVisible({ timeout: 10_000 })
    await page.waitForTimeout(300)
    await page.screenshot({ path: 'test-results/n3-gating-05-lock-predict.png' })
  })

  test('gating: hovering the locked Run shows its lock reason (#13)', async ({ page }) => {
    await open(page, 'pass')
    await compileBtn(page).click()
    await expect(predictBtn(page)).toBeEnabled({ timeout: 10_000 })
    await clearToasts(page)
    // Run is still gated until predict passes; hover surfaces "Predict must pass first".
    await page.locator('span[aria-label="Predict must pass first"]').hover()
    await expect(page.getByRole('tooltip').getByText('Predict must pass first')).toBeVisible({ timeout: 10_000 })
    await page.waitForTimeout(300)
    await page.screenshot({ path: 'test-results/n3-gating-06-lock-run.png' })
  })
})
