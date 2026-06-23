import { expect, test, type Page } from '@playwright/test'
import { SKILL_ID, SKILL_NAME, installStudioBridge, openSkillWorkspace } from './_n2bridge'

// Real-machine screenshot capture for the N2.1 canvas operations (handbook
// n2_canvas slice). Each test seeds a faithful skill-detail mock (the exact
// shape the shipping sidecar returns) and drives the real canvas UI, saving a
// screenshot into test-results/ for curation into the handbook screenshots dir.

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5199'
const SUB_PATH = '/workspace/n2-canvas-demo/phases/expand/expand-sub'

interface PhaseRow {
  id: string
  src: string
  depends_on: string[]
  mode: 'skill' | 'logic' | 'subgraph'
  path?: string | null
  field_supply?: Array<{ field: string; supplied: boolean; source: 'phase' | 'graph_input' | 'none'; producer_phase: string | null }>
}

function fileFor(p: PhaseRow): [string, string] {
  if (p.mode === 'logic') return [`phases/${p.id}/LOGIC.md`, ['---', `name: ${p.id}`, 'mode: logic', '---', '<python_callable>', p.id, '</python_callable>', '', `# ${p.id}`].join('\n')]
  if (p.mode === 'subgraph') return [`phases/${p.id}/SUBGRAPH.md`, ['---', `name: ${p.id}`, 'mode: subgraph', `path: ${SUB_PATH}`, '---', '', `# ${p.id}`].join('\n')]
  return [`phases/${p.id}/SKILL.md`, ['---', `name: ${p.id}`, 'mode: skill', 'tools:', '  - read_file', '---', '<system_prompt>', `Do ${p.id}.`, '</system_prompt>', '', '<exit_contract>', 'Call finish_task.', '</exit_contract>', '', '<step id="s1" name="gather_inputs">Collect the topic and any references.</step>', '<step id="s2" name="produce_output">Draft the output and hand off downstream.</step>', '', `# ${p.id}`].join('\n')]
}

function makeState(phases: PhaseRow[]) {
  const files: Record<string, string> = {
    'GRAPH.md': ['---', 'schema_version: v0.3.0', `name: ${SKILL_NAME}`, 'description: Canvas operations demo', 'phases:', ...phases.map((p) => `  - ${p.id}`), '---', '', `# ${SKILL_NAME}`].join('\n'),
  }
  for (const p of phases) { const [k, v] = fileFor(p); files[k] = v }
  return { phases, files, writeSeq: 0, manifest_errors: null as LintError[] | null, lint_result: null as LintResult | null }
}
type State = ReturnType<typeof makeState>

interface LintError { file: string; line: number | null; column: number | null; error_code: string; severity: string; message: string; phase_name: string | null; field_path: string | null; source_path: string | null }
interface LintResult { status: string; errors: LintError[]; phases_summary: null }

// The shipping sidecar returns a v0.3.0 manifest: `phases` is a STRING-id list
// and ALL per-phase truth (mode / depends_on / src / subgraph path / field
// supply) lives in `graph_topology`. Both the canvas RENDER (buildNodes) and the
// canvas AUTHORING (createPhaseDraft/connect/disconnect via
// phaseRefsFromSkillDetail) require this exact shape — the legacy `type:'graph'`
// PhaseDef-array shape renders but makes authoring read an empty phase list.
function detail(state: State) {
  return {
    manifest: {
      schema_version: 'v0.3.0', name: SKILL_NAME, description: 'Canvas operations demo',
      license: null, version: null, author: null, metadata: null, context_mapping: {},
      io: { inputs: { properties: { topic: { type: 'string' } } }, outputs: { properties: { summary: { type: 'string' } } } },
      phases: state.phases.map((p) => p.id),
    },
    graph_topology: state.phases.map((p) => ({ id: p.id, src: p.src, depends_on: p.depends_on, mode: p.mode, ...(p.path ? { path: p.path } : {}), ...(p.field_supply ? { field_supply: p.field_supply } : {}) })),
    node_schema_v21: {}, io_schema: {}, file_paths: {}, files: state.files,
    manifest_errors: state.manifest_errors, lint_result: state.lint_result, has_golden: false, latest_run_metadata: null,
  }
}

async function mock(page: Page, state: State, childTopology?: unknown) {
  await page.route('**/api/app/settings', (r) => r.fulfill({ contentType: 'application/json', body: '{}' }))
  await page.route('**/api/skills', (r) => r.fulfill({ contentType: 'application/json', body: JSON.stringify([{ id: SKILL_ID, name: SKILL_NAME, description: 'Canvas operations demo', phase_count: state.phases.length, has_golden: false, last_run_at: null, directory_path: null }]) }))
  await page.route(`**/api/skills/${SKILL_ID}/subgraph**`, (r) => r.fulfill({ contentType: 'application/json', body: JSON.stringify(childTopology ?? { path: SUB_PATH, name: 'Expand Sub', description: 'child', phases: [], graph_topology: [] }) }))
  await page.route(`**/api/skills/${SKILL_ID}/graph/serialize`, (r) => {
    const body = r.request().postDataJSON() as { phases: PhaseRow[] }
    // The serialize payload (SerializableGraphPhaseRef) carries only id/src/
    // depends_on/mode — NOT the per-phase `path`/`field_supply`, which the real
    // backend keeps in each phase's SUBGRAPH.md / data-gap projection on disk.
    // Preserve them by id so a serialize round-trip doesn't drop the subgraph path.
    const prior = new Map(state.phases.map((p) => [p.id, p]))
    state.phases = body.phases.map((p) => { const old = prior.get(p.id); return { ...p, mode: (p.mode ?? 'skill'), ...(old?.path ? { path: old.path } : {}), ...(old?.field_supply ? { field_supply: old.field_supply } : {}) } })
    const md = ['---', 'schema_version: v0.3.0', `name: ${SKILL_NAME}`, 'phases:', ...state.phases.map((p) => `  - ${p.id}`), '---'].join('\n')
    return r.fulfill({ contentType: 'application/json', body: JSON.stringify({ markdown_content: md, phase_count: state.phases.length, elapsed_ms: 1, current_hash: `graph-${++state.writeSeq}` }) })
  })
  await page.route(`**/api/skills/${SKILL_ID}/compile`, (r) => r.fulfill({ contentType: 'application/json', body: JSON.stringify({
    skill_id: SKILL_ID, status: 'ok', phase_count: state.phases.length, manifest_name: SKILL_NAME,
    artifact_ref: { artifact_id: 'art-1', content_hash: `sha256:${'0'.repeat(8)}`, store: 'ephemeral', version: null, manifest_ref: 'm1', source_map_ref: 's1', execution_fingerprint: 'fp00000000' },
    source_map_ref: 's1', execution_fingerprint: 'fp00000000',
  }) }))
  await page.route(`**/api/skills/${SKILL_ID}/files/**`, (r) => { const path = new URL(r.request().url()).pathname.split('/files/')[1]; const b = r.request().postDataJSON() as { content: string }; state.files[decodeURIComponent(path)] = b.content; return r.fulfill({ contentType: 'application/json', body: JSON.stringify({ path, hash: `f${++state.writeSeq}` }) }) })
  // Detail mock LAST so it can reflect mutated state on refetch.
  await page.route(`**/api/skills/${SKILL_ID}`, (r) => r.fulfill({ contentType: 'application/json', body: JSON.stringify(detail(state)) }))
}

const MAIN: PhaseRow[] = [
  { id: 'draft', src: 'phases/draft', depends_on: [], mode: 'skill' },
  { id: 'review', src: 'phases/review', depends_on: ['draft'], mode: 'logic' },
  { id: 'expand', src: 'phases/expand', depends_on: ['review'], mode: 'subgraph', path: SUB_PATH },
]

// Collapse the right-hand Copilot drawer (it has no backend here, so it just
// retries a WS and toasts) for a cleaner, canvas-focused capture.
async function hideCopilot(page: Page) {
  const hide = page.getByRole('button', { name: 'Hide Copilot' })
  if (await hide.count()) await hide.click().catch(() => {})
  // dismiss any lingering sonner toasts
  for (const x of await page.locator('[data-sonner-toast] button[aria-label]').all()) await x.click().catch(() => {})
}

async function open(page: Page, state: State, child?: unknown) {
  await installStudioBridge(page)
  await mock(page, state, child)
  await openSkillWorkspace(page, baseURL)
  await page.waitForSelector('.react-flow__node', { timeout: 10_000 })
  await hideCopilot(page)
  await page.waitForTimeout(600)
}

test.describe('N2 canvas real-machine screenshots', () => {
  test('#1 projection + #3 TB layout + #5 io endpoints', async ({ page }) => {
    const state = makeState(MAIN)
    await open(page, state)
    await expect(page.getByText('Input', { exact: true })).toBeVisible()
    await expect(page.getByText('Output', { exact: true })).toBeVisible()
    await expect(page.locator('.react-flow__node')).toHaveCount(5) // input + 3 phases + output
    await page.screenshot({ path: 'test-results/n2-01-projection.png' })
  })

  test('#2 double-click node opens its phase file', async ({ page }) => {
    const state = makeState(MAIN)
    await open(page, state)
    await page.locator('.react-flow__node').filter({ hasText: 'draft' }).dblclick()
    await expect(page.getByRole('heading', { name: 'phases/draft/SKILL.md' })).toBeVisible()
    // Wait for Monaco to finish lazy-loading and paint the file body.
    await expect(page.locator('.monaco-editor').first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('Loading...', { exact: true })).toHaveCount(0)
    await page.waitForTimeout(800)
    await page.screenshot({ path: 'test-results/n2-02-open-file.png' })
  })

  test('#4 create node = create file (Logic phase)', async ({ page }) => {
    const state = makeState(MAIN)
    await open(page, state)
    const canvas = page.locator('.react-flow')
    await canvas.click({ button: 'right', position: { x: 420, y: 300 } })
    await page.getByRole('menuitem', { name: 'Add Phase Node' }).hover()
    await page.getByRole('menuitem', { name: 'Logic Phase' }).click()
    // The new node persists alongside the existing draft/review/expand phases.
    await expect(page.locator('.react-flow__node[data-id="logic"]')).toBeVisible()
    await expect(page.locator('.react-flow__node[data-id="draft"]')).toBeVisible()
    await expect(page.locator('.react-flow__node[data-id="expand"]')).toBeVisible()
    await page.screenshot({ path: 'test-results/n2-04-create-node.png' })
  })

  test('#6 connect edge = add dependency', async ({ page }) => {
    // draft and review start with NO dependency between them.
    const unlinked: PhaseRow[] = [
      { id: 'draft', src: 'phases/draft', depends_on: [], mode: 'skill' },
      { id: 'review', src: 'phases/review', depends_on: [], mode: 'logic' },
    ]
    const state = makeState(unlinked)
    await open(page, state)
    await expect(page.locator('.react-flow__edge[data-id="draft->review"]')).toHaveCount(0)
    // Drag draft's source (bottom) handle onto review's target (top) handle to
    // wire draft → review; the canvas serializes the new depends_on.
    const source = page.locator('.react-flow__node[data-id="draft"] .react-flow__handle.source')
    const target = page.locator('.react-flow__node[data-id="review"] .react-flow__handle.target')
    await source.dragTo(target)
    await expect(page.locator('.react-flow__edge[data-id="draft->review"]')).toBeVisible({ timeout: 10_000 })
    await page.waitForTimeout(400)
    await page.screenshot({ path: 'test-results/n2-06-connect.png' })
  })

  test('#7 disconnect edge via right-click menu', async ({ page }) => {
    const state = makeState(MAIN)
    await open(page, state)
    const edge = page.locator('.react-flow__edge[data-id="draft->review"]')
    await expect(edge).toBeVisible()
    // Right-click the edge's midpoint. The edge is an SVG <g>; clicking its
    // Playwright-actionable center can miss the thin path, so drive page.mouse at
    // the measured box center (on the vertical line in TB layout).
    const box = await edge.boundingBox()
    if (!box) throw new Error('edge has no bounding box')
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2, { button: 'right' })
    await page.getByRole('menuitem', { name: 'Disconnect' }).click()
    await expect(page.locator('.react-flow__edge[data-id="draft->review"]')).toHaveCount(0, { timeout: 10_000 })
    await page.waitForTimeout(400)
    await page.screenshot({ path: 'test-results/n2-07-disconnect.png' })
  })

  test('#13 subgraph inline topology expansion', async ({ page }) => {
    const state = makeState(MAIN)
    const child = { path: SUB_PATH, name: 'Expand Sub', description: 'child graph', phases: ['plan', 'write'], graph_topology: [
      { id: 'plan', src: 'phases/plan', depends_on: [], mode: 'skill' },
      { id: 'write', src: 'phases/write', depends_on: ['plan'], mode: 'logic' },
    ] }
    await open(page, state, child)
    await page.getByRole('button', { name: 'Expand subgraph' }).click()
    await expect(page.getByRole('button', { name: 'Collapse subgraph' })).toBeVisible()
    // The child renders with the SAME recursive pipeline as the main canvas: its
    // OWN global input/output nodes + real plan/write phase nodes inside a dashed
    // container, connected by contextEdge connectors (dotted midpoint). Assert the
    // container, the child's in/out + phase nodes, and a contextEdge connector.
    await expect(page.locator('.react-flow__node[data-id="__subpreview__::group::expand"]')).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('.react-flow__node[data-id="__subpreview__::expand::__global_input__"]')).toBeVisible()
    await expect(page.locator('.react-flow__node[data-id="__subpreview__::expand::__global_output__"]')).toBeVisible()
    await expect(page.locator('.react-flow__node[data-id="__subpreview__::expand::plan"]')).toBeVisible()
    await expect(page.locator('.react-flow__node[data-id="__subpreview__::expand::write"]')).toBeVisible()
    // The child's plan → write dependency edge is a contextEdge, same as the main graph.
    await expect(page.locator('.react-flow__edge[data-id="__subpreview__::expand::plan->write"]')).toBeVisible()
    await page.waitForTimeout(500)
    await page.screenshot({ path: 'test-results/n2-13-subgraph-inline.png' })
  })

  test('#14 subgraph drilldown + breadcrumb', async ({ page }) => {
    const state = makeState(MAIN)
    const child = { path: SUB_PATH, name: 'Expand Sub', description: 'child graph', phases: ['plan', 'write'], graph_topology: [
      { id: 'plan', src: 'phases/plan', depends_on: [], mode: 'skill' },
      { id: 'write', src: 'phases/write', depends_on: ['plan'], mode: 'logic' },
    ] }
    await open(page, state, child)
    const expandNode = page.locator('.react-flow__node[data-id="expand"]')
    // Select first so the Properties panel opens and the React Flow pane finishes
    // its width reflow; only then is the node's on-screen box stable.
    await expandNode.click()
    await page.waitForTimeout(500)
    // Drill into the child graph (R9) with a real double-click at the node's
    // current center. Playwright's locator.dblclick() pre-computes the point and
    // the panel-open reflow can move the node between its two mouse-ups, so React
    // Flow never registers a node double-click; driving page.mouse at the freshly
    // measured box center avoids that.
    const box = await expandNode.boundingBox()
    if (!box) throw new Error('expand node has no bounding box')
    await page.mouse.dblclick(box.x + box.width / 2, box.y + 18)
    // The child graph (plan/write) replaces the parent; a breadcrumb appears.
    await expect(page.locator('.react-flow__node[data-id="plan"]')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('navigation').getByText(SKILL_NAME)).toBeVisible()
    await page.waitForTimeout(500)
    await page.screenshot({ path: 'test-results/n2-14-drilldown.png' })
  })

  test('#15 L3 inline step edit on agent node', async ({ page }) => {
    const state = makeState(MAIN)
    await open(page, state)
    const draft = page.locator('.react-flow__node[data-id="draft"]')
    // Open the inline L3 step editor right on the AGENT node (no Properties detour).
    // The trigger's accessible name is its aria-label ('Edit steps' → 'Collapse
    // steps' once open), which differs from the visible 'Edit steps'/'Hide steps'.
    await draft.getByRole('button', { name: 'Edit steps' }).click()
    await expect(draft.getByRole('button', { name: 'Collapse steps' })).toBeVisible()
    // The two `<step>` blocks render as editable name+content rows on the canvas.
    await expect(draft.getByText('Steps', { exact: true })).toBeVisible()
    await expect(draft.getByRole('textbox', { name: 'Step s1 name' })).toHaveValue('gather_inputs')
    await expect(draft.getByRole('textbox', { name: 'Step s2 name' })).toHaveValue('produce_output')
    await page.waitForTimeout(400)
    await page.screenshot({ path: 'test-results/n2-15-l3-steps.png' })
  })

  test('#9 cycle detection full-screen block', async ({ page }) => {
    const cyclic: PhaseRow[] = [
      { id: 'a', src: 'phases/a', depends_on: ['b'], mode: 'skill' },
      { id: 'b', src: 'phases/b', depends_on: ['a'], mode: 'logic' },
    ]
    const state = makeState(cyclic)
    await installStudioBridge(page)
    await mock(page, state)
    await openSkillWorkspace(page, baseURL)
    await page.waitForTimeout(1200)
    await page.screenshot({ path: 'test-results/n2-09-cycle.png' })
  })

  test('#10 data-gap node compile error', async ({ page }) => {
    const gap: PhaseRow[] = [
      { id: 'draft', src: 'phases/draft', depends_on: [], mode: 'skill' },
      { id: 'review', src: 'phases/review', depends_on: ['draft'], mode: 'logic', field_supply: [{ field: 'missing_field', supplied: false, source: 'none', producer_phase: null }] },
    ]
    const state = makeState(gap)
    await open(page, state)
    await page.waitForTimeout(600)
    await page.screenshot({ path: 'test-results/n2-10-data-gap.png' })
  })

  test('#8 reconnect edge endpoint to a different node', async ({ page }) => {
    // draft → review exists; drag the edge's target endpoint off review onto a
    // third node `extra`, so the dependency moves (old target dropped, new added).
    const phases: PhaseRow[] = [
      { id: 'draft', src: 'phases/draft', depends_on: [], mode: 'skill' },
      { id: 'review', src: 'phases/review', depends_on: ['draft'], mode: 'logic' },
      { id: 'extra', src: 'phases/extra', depends_on: [], mode: 'logic' },
    ]
    const state = makeState(phases)
    await open(page, state)
    const edge = page.locator('.react-flow__edge[data-id="draft->review"]')
    await expect(edge).toBeVisible()
    await edge.hover({ force: true })
    const updater = edge.locator('.react-flow__edgeupdater-target')
    const newTarget = page.locator('.react-flow__node[data-id="extra"] .react-flow__handle.target')
    await updater.dragTo(newTarget, { force: true })
    await expect(page.locator('.react-flow__edge[data-id="draft->extra"]')).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('.react-flow__edge[data-id="draft->review"]')).toHaveCount(0)
    await page.waitForTimeout(400)
    await page.screenshot({ path: 'test-results/n2-08-reconnect.png' })
  })

  test('#11 sequential-overwrite conflict warning', async ({ page }) => {
    // draft and review (review depends on draft) BOTH declare output field
    // `result`; since draft is review's ancestor, writing `result` again is a
    // sequential overwrite → the canvas raises the Allow-Overwrite / Cancel warning.
    const phases: PhaseRow[] = [
      { id: 'draft', src: 'phases/draft', depends_on: [], mode: 'skill' },
      { id: 'review', src: 'phases/review', depends_on: ['draft'], mode: 'logic' },
    ]
    const state = makeState(phases)
    state.files['phases/draft/SKILL.md'] = ['---', 'name: draft', 'mode: skill', 'io:', '  outputs:', '    properties:', '      result:', '        type: string', '---', '<system_prompt>', 'Draft.', '</system_prompt>', '', '<exit_contract>Call finish_task.</exit_contract>'].join('\n')
    state.files['phases/review/LOGIC.md'] = ['---', 'name: review', 'mode: logic', 'io:', '  outputs:', '    properties:', '      result:', '        type: string', '---', '<python_callable>review</python_callable>'].join('\n')
    await open(page, state)
    await expect(page.getByText('Sequential Overwrite Detected')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('button', { name: 'Allow Overwrite' })).toBeVisible()
    await page.waitForTimeout(400)
    await page.screenshot({ path: 'test-results/n2-11-seq-overwrite.png' })
  })

  test('#12 failure path: broken phase surfaces a per-node error badge', async ({ page }) => {
    // When the backend reports a phase as broken (invalid frontmatter →
    // manifest_error), the canvas projects it onto THAT node's error badge with
    // the `field · L<line> — message` detail, so the author sees which phase
    // failed and can open the file. This is one of the #12 failure-path surfaces.
    const phases: PhaseRow[] = [
      { id: 'draft', src: 'phases/draft', depends_on: [], mode: 'skill' },
      { id: 'review', src: 'phases/review', depends_on: ['draft'], mode: 'logic' },
    ]
    const state = makeState(phases)
    const err: LintError = { file: 'phases/review/LOGIC.md', line: 4, column: null, error_code: 'F-v3-201', severity: 'error', message: 'Invalid YAML frontmatter', phase_name: 'review', field_path: 'io', source_path: null }
    state.manifest_errors = [err]
    state.lint_result = { status: 'failed', errors: [err], phases_summary: null }
    await page.addInitScript((id) => window.sessionStorage.setItem(`studio-lint-status-${id}`, 'failed'), SKILL_ID)
    await open(page, state)
    await expect(page.locator('[aria-label*="io · L4 — Invalid YAML frontmatter"]').first()).toBeVisible({ timeout: 10_000 })
    await page.waitForTimeout(400)
    await page.screenshot({ path: 'test-results/n2-12-failure-path.png' })
  })
})
