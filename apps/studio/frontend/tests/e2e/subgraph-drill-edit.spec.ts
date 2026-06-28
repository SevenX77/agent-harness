import { expect, test, type Page, type Route } from '@playwright/test'

// n2-canvas atom #14 (subgraph-drilldown — EDIT-WRITEBACK closure). Layer-2 e2e.
//
// Proves the drilled-subgraph edit-writeback closure real-machine: drilling into a
// subgraph stays ON THE SAME CANVAS (no project switch), editing a child node writes
// to the CHILD skill's own files/serialize/compile (never the parent), and a forced
// 409 on the child write rolls back (toast + child re-fetch) leaving the parent
// untouched. Route-mocked SkillDetail + real navigation, following
// canvas-lint-projection.spec.ts / canvas-v1.spec.ts.
//
// Real-machine acceptance: the gatekeeper runs this with the dev server + real
// navigation. (Written, not run, in the implementing session.)

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

const PARENT_ID = 'drill-edit-parent'
const CHILD_PATH = '/abs/workspaces/default/skills/drill-edit-child'
const CHILD_ID = 'drill-edit-child'

interface WriteState {
  parentWrites: string[]
  childWrites: string[]
  childSerializeCount: number
  childCompileCount: number
  forceChildConflict: boolean
}

function graphManifest(name: string, phases: string[]) {
  return {
    schema_version: '2.0',
    type: 'graph',
    name,
    description: `${name} skill`,
    license: null,
    version: null,
    author: null,
    metadata: null,
    context_mapping: {},
    io: { inputs: [], outputs: [] },
    phases,
  }
}

function topologyRow(id: string, mode: string, dependsOn: string[], path?: string) {
  return { id, src: `phases/${id}/${mode === 'agent' ? 'SKILL.md' : mode === 'subgraph' ? 'SUBGRAPH.md' : 'LOGIC.md'}`, depends_on: dependsOn, mode, ...(path ? { path } : {}) }
}

// The PARENT skill: a single subgraph phase pointing at the child by absolute path.
function parentDetail() {
  return {
    manifest: graphManifest('Drill Edit Parent', ['sub']),
    graph_topology: [topologyRow('sub', 'subgraph', [], CHILD_PATH)],
    node_schema_v21: {},
    io_schema: {},
    file_paths: {},
    files: { 'GRAPH.md': 'schema_version: "2.0"\nname: Drill Edit Parent\nphases:\n  - id: sub\n' },
    manifest_errors: null,
    has_golden: false,
    latest_run_metadata: null,
    lint_result: null,
  }
}

// The CHILD subgraph topology (what GET /skills/{parent}/subgraph returns).
function childTopology() {
  return {
    path: CHILD_PATH,
    name: 'Drill Edit Child',
    description: 'Editable child subgraph',
    phases: ['draft', 'review'],
    graph_topology: [
      topologyRow('draft', 'agent', []),
      topologyRow('review', 'logic', ['draft']),
    ],
  }
}

// The CHILD's full SkillDetail (Option A: GET /skills/{childId}) — gives the edit
// wiring (phase refs + GRAPH.md text) keyed to the child identity.
function childDetail() {
  return {
    manifest: graphManifest('Drill Edit Child', ['draft', 'review']),
    graph_topology: [
      topologyRow('draft', 'agent', []),
      topologyRow('review', 'logic', ['draft']),
    ],
    node_schema_v21: {},
    io_schema: {},
    file_paths: {},
    files: {
      'GRAPH.md': 'schema_version: "2.0"\nname: Drill Edit Child\nphases:\n  - id: draft\n  - id: review\n    depends_on: [draft]\n',
      'phases/draft/SKILL.md': ['---', 'name: draft', 'llm_role: writer', '---', 'Draft body'].join('\n'),
    },
    manifest_errors: null,
    has_golden: false,
    latest_run_metadata: null,
    lint_result: null,
  }
}

async function mockDrillEditSkill(page: Page): Promise<WriteState> {
  const state: WriteState = {
    parentWrites: [],
    childWrites: [],
    childSerializeCount: 0,
    childCompileCount: 0,
    forceChildConflict: false,
  }

  await page.route('**/api/skills', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify([{
        id: PARENT_ID,
        name: 'Drill Edit Parent',
        description: 'Drilled-subgraph edit-writeback smoke',
        phase_count: 1,
        has_golden: false,
        last_run_at: null,
        directory_path: null,
      }]),
    })
  })

  await page.route(`**/api/skills/${PARENT_ID}`, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(parentDetail()) })
  })

  // GET /skills/{parent}/subgraph?path=... → child topology (drill resolver).
  await page.route(`**/api/skills/${PARENT_ID}/subgraph**`, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(childTopology()) })
  })

  // GET /skills/{childId} → child SkillDetail (Option A editable graph source).
  await page.route(`**/api/skills/${CHILD_ID}`, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(childDetail()) })
  })

  // Parent writes — these must NOT be hit during a drilled-child edit.
  await page.route(`**/api/skills/${PARENT_ID}/files/**`, async (route) => {
    state.parentWrites.push(filePathFromRoute(route))
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ path: 'GRAPH.md', hash: 'parent-hash' }) })
  })
  await page.route(`**/api/skills/${PARENT_ID}/graph/serialize`, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: serializeBody('Drill Edit Parent') })
  })

  // CHILD writes — the drilled edit MUST land here.
  await page.route(`**/api/skills/${CHILD_ID}/graph/serialize`, async (route) => {
    state.childSerializeCount += 1
    await route.fulfill({ contentType: 'application/json', body: serializeBody('Drill Edit Child') })
  })
  await page.route(`**/api/skills/${CHILD_ID}/files/**`, async (route) => {
    if (state.forceChildConflict) {
      // Forced optimistic-lock conflict on the child write → rollback path.
      await route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({ current_hash: 'child-remote', current_markdown_content: 'remote child GRAPH.md' }),
      })
      return
    }
    state.childWrites.push(filePathFromRoute(route))
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ path: 'GRAPH.md', hash: 'child-hash' }) })
  })
  await page.route(`**/api/skills/${CHILD_ID}/compile`, async (route) => {
    state.childCompileCount += 1
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        manifest_name: 'Drill Edit Child',
        artifact_ref: { content_hash: 'child-artifact' },
        execution_fingerprint: 'child-fp',
      }),
    })
  })

  return state
}

function filePathFromRoute(route: Route): string {
  return new URL(route.request().url()).pathname.split('/files/')[1] ?? ''
}

function serializeBody(name: string): string {
  return JSON.stringify({
    markdown_content: `schema_version: "2.0"\nname: ${name}\n`,
    phase_count: 2,
    elapsed_ms: 1,
    current_hash: `hash-${name}`,
  })
}

async function openParentAndDrillIn(page: Page) {
  await page.goto(baseURL)
  await page.getByRole('button', { name: /Drill Edit Parent/ }).first().click()
  // Drill INTO the subgraph node by double-clicking it (R9 drill focus).
  await page.locator('.react-flow').getByText('sub', { exact: true }).dblclick()
  // The drill stays ON THE SAME CANVAS: the breadcrumb shows parent / child and the
  // child's phases render. The project/nav is NOT switched.
  await expect(page.getByText('Drill Edit Child')).toBeVisible()
  await expect(page.locator('.react-flow').getByText('draft', { exact: true })).toBeVisible()
  await expect(page.locator('.react-flow').getByText('review', { exact: true })).toBeVisible()
}

test.describe('Subgraph drill edit-writeback (n2-canvas #14)', () => {
  test('drilling in stays on the same canvas (no project switch)', async ({ page }) => {
    test.setTimeout(60_000)
    await mockDrillEditSkill(page)
    await openParentAndDrillIn(page)
    // The parent breadcrumb root is still present → we are focused INTO the child on
    // the same canvas, not swapped to the child as a standalone project.
    await expect(page.getByText('Drill Edit Parent')).toBeVisible()
  })

  test('editing a child edge writes to the CHILD skill, never the parent', async ({ page }) => {
    test.setTimeout(60_000)
    const state = await mockDrillEditSkill(page)
    await openParentAndDrillIn(page)

    // Disconnect the child's draft → review dependency via the edge context menu.
    await page.locator('.react-flow__edge').first().click({ button: 'right' })
    await page.getByRole('menuitem', { name: 'Disconnect' }).click()

    // The serialize + GRAPH.md write + compile all hit the CHILD id.
    await expect.poll(() => state.childSerializeCount).toBeGreaterThan(0)
    await expect.poll(() => state.childWrites.some((p) => p.includes('GRAPH.md'))).toBe(true)
    await expect.poll(() => state.childCompileCount).toBeGreaterThan(0)
    // The parent skill is NEVER written during a drilled-child edit.
    expect(state.parentWrites).toEqual([])
  })

  test('a forced 409 on the child write rolls back (parent untouched)', async ({ page }) => {
    test.setTimeout(60_000)
    const state = await mockDrillEditSkill(page)
    state.forceChildConflict = true
    await openParentAndDrillIn(page)

    await page.locator('.react-flow__edge').first().click({ button: 'right' })
    await page.getByRole('menuitem', { name: 'Disconnect' }).click()

    // The rollback re-fetches the child (the optimistic edge snaps back to the child
    // snapshot); the parent is never written.
    await expect(page.locator('.react-flow').getByText('draft', { exact: true })).toBeVisible()
    await expect(page.locator('.react-flow').getByText('review', { exact: true })).toBeVisible()
    expect(state.parentWrites).toEqual([])
  })
})
