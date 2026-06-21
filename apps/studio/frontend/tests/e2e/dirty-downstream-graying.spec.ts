import { expect, test, type Page } from '@playwright/test'

// F-n5 (n5-node atom #3, spec F3): after a real Run fails, an upstream edit invalidates the
// affected DOWNSTREAM nodes' checkpoints. Their node-level Resume must AUTO-gray — without the
// user having to select the failed node first — while unrelated side-branches stay runnable.
// The backend per-node `affected_downstream` slice (B1) drives exactly which nodes gray.
//
// Real-machine acceptance: the gatekeeper runs this against the dev server with a real failed Run.
// Here the validity endpoint is mocked to return the per-node slice so the FE auto-derive + graying
// is exercised end-to-end (the auto-fire is the FE behavior under test, not the backend compute).

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

const SKILL_ID = 'dirty-downstream-smoke'
const RUN_ID = 'run-1'

function failEvent(phase: string) {
  return {
    schema_version: '1.0',
    event_type: 'validation_fail',
    timestamp: '2026-06-18T00:00:00Z',
    run_id: RUN_ID,
    phase_name: phase,
    checkpoint_id: `cp-${phase}`,
    checkpoint_ns: `agent:${phase}`,
    errors: ['model alias is unknown'],
  }
}

async function mockDirtyDownstreamSkill(page: Page) {
  await page.route('**/api/skills', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify([{
        id: SKILL_ID,
        name: 'Dirty Downstream Smoke',
        description: 'Dirty-downstream graying smoke skill',
        phase_count: 3,
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
          name: 'Dirty Downstream Smoke',
          description: 'Dirty-downstream graying smoke skill',
          license: null,
          version: null,
          author: null,
          metadata: null,
          context_mapping: {},
          io: { inputs: [], outputs: [] },
          phases: [
            { name: 'draft', mode: 'llm', model_override: null, depends_on: undefined, prompt: 'Draft', user_prompt_template: null, agent_tools: [], steps: [], domain_protocols: [], references: [], few_shot_examples: [], context_access: ['working_memory'], llm_role: 'Agent', adopted_persona: null, max_iterations: null, max_retries: null, max_nudges: null, dead_end_threshold: null, validator: null, validator_optional: false, retry_target: null, hoist_to: null, output_schema: null, output_example: null, output_schema_md: null, output_example_md: null },
            { name: 'review', mode: 'logic', model_override: null, depends_on: 'draft', execute_steps: ['validate'], validator: null },
            { name: 'sidebar', mode: 'logic', model_override: null, depends_on: undefined, execute_steps: ['unrelated'], validator: null },
          ],
        },
        file_paths: {},
        has_golden: false,
        latest_run_metadata: null,
        lint_result: null,
      }),
    })
  })

  await page.route(`**/api/skills/${SKILL_ID}/runs/${RUN_ID}`, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        metadata: { run_id: RUN_ID, status: 'failed', started_at: '2026-06-18T00:00:00Z', metrics: null, input_summary: null },
        input_data: {},
        // draft failed; review depends on draft; sidebar is unrelated.
        events: [failEvent('draft')],
        final_context: null,
        artifacts: [],
      }),
    })
  })

  // The auto edit-watcher fires the validity probe anchored on the failed `draft` node. The backend
  // per-node slice reaches draft + review; sidebar is absent (unrelated branch stays runnable).
  await page.route(`**/api/skills/${SKILL_ID}/runs/${RUN_ID}/resume/validity`, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        run_id: RUN_ID,
        resume_allowed: false,
        reason: 'dirty_upstream',
        checkpoint_id: 'cp-draft',
        checkpoint_ns: 'agent:draft',
        resume_from_node_id: 'draft',
        resume_to_node_id: null,
        dirty_fields: ['content_hash'],
        dirty_node_ids: ['draft', 'review'],
        affected_downstream: ['draft', 'review'],
        snapshot_content_hash: 'snap',
        current_content_hash: 'current',
        snapshot_execution_fingerprint: null,
        current_execution_fingerprint: null,
      }),
    })
  })
}

test.describe('Dirty-downstream auto graying (F-n5 atom #3)', () => {
  test('grays the affected-downstream nodes automatically after an upstream edit; side branch stays normal', async ({ page }) => {
    test.setTimeout(60_000)
    await page.addInitScript((skillId) => {
      window.sessionStorage.setItem(`studio-lint-status-${skillId}`, 'passed')
      class MockWebSocket extends EventTarget {
        static CONNECTING = 0
        static OPEN = 1
        static CLOSING = 2
        static CLOSED = 3
        readyState = MockWebSocket.OPEN
        onopen: ((event: Event) => void) | null = null
        onclose: ((event: Event) => void) | null = null
        onmessage: ((event: MessageEvent) => void) | null = null
        onerror: ((event: Event) => void) | null = null
        constructor() {
          super()
          setTimeout(() => {
            this.readyState = MockWebSocket.OPEN
            this.onopen?.(new Event('open'))
          }, 0)
        }
        close() {
          this.readyState = MockWebSocket.CLOSED
        }
        send() {}
      }
      Object.defineProperty(window, 'WebSocket', { value: MockWebSocket })
    }, SKILL_ID)
    await mockDirtyDownstreamSkill(page)

    // Open the failed run directly — the auto edit-watcher derives the affected set without a manual
    // node selection (the F-n5 behavior: graying no longer depends on selecting the failed node).
    await page.goto(`${baseURL}/#/skill/${SKILL_ID}/run/${RUN_ID}`)

    // The affected-downstream nodes gray automatically.
    await expect(page.locator('[data-dirty-downstream="true"]')).toHaveCount(2)
    await expect(page.getByLabel('Resume unavailable: upstream changed').first()).toBeVisible()

    // Exactly the affected set is grayed; the unrelated side branch is NOT.
    const grayedLabels = await page.locator('[data-dirty-downstream="true"]').allInnerTexts()
    expect(grayedLabels.join(' ')).toContain('draft')
    expect(grayedLabels.join(' ')).toContain('review')
    expect(grayedLabels.join(' ')).not.toContain('sidebar')
  })
})
