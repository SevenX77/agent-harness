import { expect, test, type Page } from '@playwright/test'

// n2-properties #19 (atom #19): a LOGIC node's Properties form must surface a
// NON-blocking hint telling the author that the fields an action may write back
// are bounded by io.outputs, and that those field boundaries are edited in the
// I/O panel (toolbar tab 3) — not in Properties. This is a real-machine check:
// it opens the app, selects a logic node, and reads the rendered hint from the
// live Properties panel.
//
// NOTE: this spec is written for the gatekeeper to run during real-machine
// acceptance; it is NOT run by the implementing agent.

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

async function mockLogicPropsSkill(page: Page) {
  const phases = [
    { id: 'draft', src: 'phases/draft', depends_on: [], mode: 'skill' },
    { id: 'review', src: 'phases/review', depends_on: ['draft'], mode: 'logic' },
  ]
  const files: Record<string, string> = {
    'GRAPH.md': [
      'schema_version: "2.1"',
      'name: Logic Props Smoke',
      'description: Logic props smoke skill',
      'io:',
      '  outputs:',
      '    properties:',
      '      summary:',
      '        type: string',
    ].join('\n'),
    'phases/draft/SKILL.md': [
      '---',
      'name: draft',
      'llm_role: writer',
      '---',
      '<role>Draft the story.</role>',
    ].join('\n'),
    'phases/review/LOGIC.md': [
      '---',
      'name: review',
      'actions:',
      '  - normalize_summary',
      '---',
      '# Review',
    ].join('\n'),
  }

  const skillDetail = () => ({
    manifest: {
      schema_version: '2.1',
      name: 'Logic Props Smoke',
      description: 'Logic props smoke skill',
      phases: phases.map(({ id, src, depends_on }) => ({ id, src, depends_on })),
    },
    graph_topology: phases,
    node_schema_v21: {},
    io_schema: {},
    file_paths: {},
    files,
    manifest_errors: null,
    has_golden: false,
    latest_run_metadata: null,
    lint_result: null,
  })

  await page.route('**/api/skills', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify([{
        id: 'logic-props-smoke',
        name: 'Logic Props Smoke',
        description: 'Logic props smoke skill',
        phase_count: phases.length,
        has_golden: false,
        last_run_at: null,
        directory_path: null,
      }]),
    })
  })

  await page.route('**/api/skills/logic-props-smoke', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(skillDetail()),
    })
  })
}

async function openSkill(page: Page) {
  await page.goto(baseURL)
  await expect(page.getByText('Logic Props Smoke').first()).toBeVisible()
  await page.getByRole('button', { name: /Logic Props Smoke/ }).first().click()
}

test.describe('Properties — logic io.outputs hint (n2-properties #19)', () => {
  test('logic node Properties shows a non-blocking hint pointing to the I/O panel', async ({ page }) => {
    await mockLogicPropsSkill(page)
    await openSkill(page)

    // Select the logic node ('review' → phases/review/LOGIC.md).
    await page.getByText('review', { exact: true }).click()
    await expect(page.getByText('Properties', { exact: true })).toBeVisible()

    // Logic whitelist fields are present (the hint is additive, not a replacement).
    await expect(page.getByText('Actions', { exact: true })).toBeVisible()
    await expect(page.getByText('Validator', { exact: true })).toBeVisible()

    // The non-blocking io.outputs boundary hint pointing to the I/O panel.
    await expect(page.getByText(/io\.outputs/)).toBeVisible()
    await expect(page.getByText(/I\/O panel/)).toBeVisible()

    // The hint is informational — it does not add an editable output field here.
    await expect(page.locator('#phase-outputs')).toHaveCount(0)
  })
})
