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

async function mockCanvasAuthoringSkill(page: Page) {
  let writeCount = 0
  const state = {
    phases: [
      { id: 'draft', src: 'phases/draft', depends_on: [], mode: 'skill' },
      { id: 'review', src: 'phases/review', depends_on: ['draft'], mode: 'logic' },
    ],
    files: {
      'GRAPH.md': [
        'schema_version: "2.1"',
        'name: Canvas Authoring Smoke',
        'description: Canvas authoring smoke skill',
      ].join('\n'),
      'phases/draft/SKILL.md': [
        '---',
        'name: draft',
        'mode: skill',
        'tools:',
        '  - read_file',
        '---',
        '<system_prompt>',
        'Draft the story.',
        '</system_prompt>',
        '',
        '<exit_contract>',
        'Call finish_task.',
        '</exit_contract>',
        '',
        '# Draft',
      ].join('\n'),
      'phases/review/LOGIC.md': [
        '---',
        'name: review',
        'mode: logic',
        '---',
        '<python_callable>',
        'review',
        '</python_callable>',
        '',
        '# Review',
      ].join('\n'),
    } as Record<string, string>,
  }

  const skillDetail = () => ({
    manifest: {
      schema_version: '2.1',
      name: 'Canvas Authoring Smoke',
      description: 'Canvas authoring smoke skill',
      phases: state.phases.map(({ id, src, depends_on }) => ({ id, src, depends_on })),
    },
    graph_topology: state.phases,
    node_schema_v21: {},
    io_schema: {},
    file_paths: {},
    files: state.files,
    manifest_errors: null,
    has_golden: false,
    latest_run_metadata: null,
    lint_result: null,
  })

  await page.route('**/api/skills', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify([{
        id: 'canvas-authoring-smoke',
        name: 'Canvas Authoring Smoke',
        description: 'Canvas authoring smoke skill',
        phase_count: state.phases.length,
        has_golden: false,
        last_run_at: null,
        directory_path: null,
      }]),
    })
  })

  await page.route('**/api/skills/canvas-authoring-smoke', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(skillDetail()),
    })
  })

  await page.route('**/api/skills/canvas-authoring-smoke/files/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
      .split('/files/')[1]
      .split('/')
      .map(decodeURIComponent)
      .join('/')
    const body = request.postDataJSON() as { content: string }
    state.files[path] = body.content
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ path, hash: `hash-${++writeCount}` }),
    })
  })

  await page.route('**/api/skills/canvas-authoring-smoke/graph/serialize', async (route) => {
    const body = route.request().postDataJSON() as {
      phases: Array<{ id: string; src: string; depends_on: string[]; mode: 'logic' | 'skill' | 'subgraph' }>
    }
    state.phases = body.phases
    const markdown = [
      'schema_version: "2.1"',
      'name: Canvas Authoring Smoke',
      'description: Canvas authoring smoke skill',
      'phases:',
      ...state.phases.map((phase) => `  - id: ${phase.id}\n    src: ${phase.src}\n    depends_on: ${JSON.stringify(phase.depends_on)}`),
    ].join('\n')
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        markdown_content: markdown,
        phase_count: state.phases.length,
        elapsed_ms: 1,
        current_hash: `graph-${writeCount}`,
      }),
    })
  })

  return state
}

async function openAuthoringSkill(page: Page) {
    await page.goto(baseURL)
    await expect(page.getByText('Canvas Authoring Smoke').first()).toBeVisible()
    await page.getByRole('button', { name: /Canvas Authoring Smoke/ }).first().click()
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
    await expect(page.getByRole('button', { name: 'View edge trace data' }).first()).toBeVisible()

    await page.getByText('draft', { exact: true }).click()
    await expect(page.getByText('Properties', { exact: true })).toBeVisible()
    await expect(page.getByText('Phase ID', { exact: true })).toBeVisible()

    await page.screenshot({ path: 'test-results/canvas-v1-desktop-initial.png', fullPage: false })

    await expect(page.getByRole('button', { name: 'Expand subgraph' })).toBeVisible()
    await page.getByRole('button', { name: 'Expand subgraph' }).click()
    await expect(page.getByRole('button', { name: 'Collapse subgraph' })).toBeVisible()
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

test.describe('Canvas authoring interactions', () => {
  test('edits phase frontmatter from Properties and creates phase nodes from the canvas menu', async ({ page }) => {
    const state = await mockCanvasAuthoringSkill(page)
    await openAuthoringSkill(page)

    await page.getByText('draft', { exact: true }).click()
    await expect(page.getByText('Properties', { exact: true })).toBeVisible()
    await expect(page.getByText('System prompt', { exact: true })).toBeVisible()

    const prompt = page.getByRole('textbox', { name: 'System prompt', exact: true })
    await prompt.fill('Updated draft prompt.')
    await page.getByRole('button', { name: 'Save' }).click()
    await expect(prompt).toHaveValue('Updated draft prompt.')
    expect(state.files['phases/draft/SKILL.md']).toContain('<system_prompt>\nUpdated draft prompt.\n</system_prompt>')

    const canvas = page.locator('.react-flow')
    await canvas.click({ button: 'right', position: { x: 360, y: 260 } })
    await page.getByRole('menuitem', { name: 'Add Phase Node' }).hover()
    await page.getByRole('menuitem', { name: 'Logic Phase' }).click()
    await expect(page.getByText('logic', { exact: true })).toBeVisible()

    await canvas.click({ button: 'right', position: { x: 400, y: 280 } })
    await page.getByRole('menuitem', { name: 'Add Phase Node' }).hover()
    await page.getByRole('menuitem', { name: 'Agent Phase' }).click()
    await expect(page.getByText('agent', { exact: true })).toBeVisible()

    await canvas.click({ button: 'right', position: { x: 420, y: 300 } })
    await page.getByRole('menuitem', { name: 'Add Phase Node' }).hover()
    await page.getByRole('menuitem', { name: 'Subgraph Phase' }).click()
    await expect(page.getByText('subgraph', { exact: true })).toBeVisible()

    expect(state.files['phases/logic/LOGIC.md']).toContain('mode: logic')
    expect(state.files['phases/logic/LOGIC.md']).toContain('<python_callable>')
    expect(state.files['phases/agent/SKILL.md']).toContain('mode: skill')
    expect(state.files['phases/agent/SKILL.md']).toContain('<exit_contract>')
    expect(state.files['phases/subgraph/SUBGRAPH.md']).toContain('mode: subgraph')
    expect(state.files['phases/subgraph/SUBGRAPH.md']).toContain('target_skill:')
    expect(state.files['GRAPH.md']).toContain('subgraph')

    await page
      .locator('.react-flow__handle-right[data-nodeid="draft"]')
      .dragTo(page.locator('.react-flow__handle-left[data-nodeid="logic"]'))
    await expect.poll(() => state.phases.find((phase) => phase.id === 'logic')?.depends_on).toEqual(['draft'])

    await page.locator('[data-edge-source="draft"][data-edge-target="logic"]').click({ button: 'right' })
    await page.getByRole('menuitem', { name: 'Disconnect' }).click()
    await expect.poll(() => state.phases.find((phase) => phase.id === 'logic')?.depends_on).toEqual([])

    await page.screenshot({ path: 'test-results/canvas-authoring-after-create.png', fullPage: false })
  })

  test('keeps canvas authoring actions available in split editor mode', async ({ page }) => {
    const state = await mockCanvasAuthoringSkill(page)
    await openAuthoringSkill(page)

    await page.locator('.react-flow').getByText('draft', { exact: true }).dblclick()
    await expect(page.getByRole('heading', { name: 'phases/draft/SKILL.md' })).toBeVisible()

    const canvas = page.locator('.react-flow')
    await canvas.click({ button: 'right', position: { x: 360, y: 120 } })
    await page.getByRole('menuitem', { name: 'Add Phase Node' }).hover()
    await page.getByRole('menuitem', { name: 'Logic Phase' }).click()

    await expect.poll(() => state.phases.some((phase) => phase.id === 'logic')).toBe(true)
    await expect(canvas.getByText('logic', { exact: true })).toBeVisible()
    await page.screenshot({ path: 'test-results/canvas-authoring-split-editor.png', fullPage: false })
  })
})
