import { expect, test } from '@playwright/test'
import type { Page, Request } from '@playwright/test'

const SKILL_ID = 'smoke-skill'

const SKILL_SUMMARY = {
  id: SKILL_ID,
  name: 'Smoke Skill',
  description: 'e2e collab smoke',
  phase_count: 1,
  has_golden: false,
  last_run_at: null,
  directory_path: '/tmp/smoke',
  config_mismatch: null,
}

const SKILL_DETAIL = {
  manifest: {
    schema_version: '2.0',
    type: 'graph',
    name: 'Smoke Skill',
    description: 'e2e collab smoke',
    license: null,
    version: null,
    author: null,
    metadata: null,
    context_mapping: {},
    io: { inputs: [], outputs: [] },
    phases: [],
  },
  file_paths: {},
  has_golden: false,
  latest_run_metadata: null,
  lint_result: null,
}

async function mockSkillsList(page: Page) {
  await page.route('**/api/skills', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([SKILL_SUMMARY]),
      })
      return
    }
    await route.continue()
  })
}

async function mockSkillDetail(page: Page) {
  await page.route(`**/api/skills/${SKILL_ID}`, async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SKILL_DETAIL),
      })
      return
    }
    await route.continue()
  })
}

async function mockCopilotCredentials(page: Page) {
  await page.route('**/api/copilot/credentials', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        active_backend: 'claude',
        backends: {
          claude: { has_key: true },
          deepseek: { has_key: false },
          gemini: { has_key: false, V1_5_PLACEHOLDER: true },
          openai: { has_key: false, V1_5_PLACEHOLDER: true },
        },
      }),
    })
  })
}

async function mockSync(
  page: Page,
  response: Record<string, unknown>,
  status = 200,
) {
  await page.route(`**/api/skills/${SKILL_ID}/sync`, async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(response),
      })
      return
    }
    await route.continue()
  })
}

async function mockPublish(
  page: Page,
  response: Record<string, unknown>,
  status = 200,
) {
  await page.route(`**/api/skills/${SKILL_ID}/publish`, async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(response),
      })
      return
    }
    await route.continue()
  })
}

async function enterWorkspace(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: /Smoke Skill/ }).first().click()
  await expect(page.getByRole('button', { name: 'Save to Team' })).toBeVisible()
}

function syncRequestMatcher(request: Request) {
  return (
    request.url().includes(`/api/skills/${SKILL_ID}/sync`) &&
    request.method() === 'POST'
  )
}

function publishRequestMatcher(request: Request) {
  return (
    request.url().includes(`/api/skills/${SKILL_ID}/publish`) &&
    request.method() === 'POST'
  )
}

test.describe('Team collaboration buttons', () => {
  test.beforeEach(async ({ page }) => {
    await mockCopilotCredentials(page)
    await mockSkillsList(page)
    await mockSkillDetail(page)
  })

  test('Save to Team success shows business toast and sends save_to_team action', async ({ page }) => {
    await mockSync(page, {
      status: 'ok',
      message: 'Pushed',
      pr_url: null,
      extra: {},
    })

    await enterWorkspace(page)

    const requestPromise = page.waitForRequest(syncRequestMatcher)
    await page.getByRole('button', { name: 'Save to Team' }).click()
    const request = await requestPromise

    expect(JSON.parse(request.postData() ?? '{}')).toMatchObject({
      action: 'save_to_team',
    })
    await expect(page.getByText('Saved to team')).toBeVisible({ timeout: 5000 })
  })

  test('Sync from Team surfaces latest_restored snapshot toast', async ({ page }) => {
    await mockSync(page, {
      status: 'ok',
      message: 'Synced',
      pr_url: null,
      extra: { latest_restored: true },
    })

    await enterWorkspace(page)
    await page.getByRole('button', { name: 'Sync from Team' }).click()

    await expect(page.getByText(/latest snapshot/i)).toBeVisible({ timeout: 5000 })
  })

  test('Submit for Review requires_review surfaces PR url toast', async ({ page }) => {
    const prUrl = 'https://gitea.example/repo/pulls/42'
    await mockSync(page, {
      status: 'requires_review',
      message: 'Review required',
      pr_url: prUrl,
      extra: {},
    })

    await enterWorkspace(page)

    // Override window.prompt before triggering — Header calls it twice (devBranch, prTitle).
    // Returning the default value the app provides keeps the request body shape intact.
    await page.evaluate(() => {
      window.prompt = (_message?: string, defaultValue?: string) =>
        defaultValue ?? 'mocked-input'
    })

    const requestPromise = page.waitForRequest(syncRequestMatcher)
    await page.getByRole('button', { name: 'Submit for Review' }).click()
    const request = await requestPromise

    expect(JSON.parse(request.postData() ?? '{}')).toMatchObject({
      action: 'submit_for_review',
      dev_branch: `review/${SKILL_ID}`,
      pr_title: `Review ${SKILL_ID}`,
    })

    await expect(page.getByText(/PR for review/i)).toBeVisible({ timeout: 5000 })
    await expect(page.getByText(prUrl)).toBeVisible({ timeout: 5000 })
  })

  test('Release to Production success shows artifact id toast', async ({ page }) => {
    await mockPublish(page, {
      status: 'ok',
      message: 'Published',
      artifact_id: 'art-999',
      extra: {},
    })

    await enterWorkspace(page)

    const requestPromise = page.waitForRequest(publishRequestMatcher)
    await page.getByRole('button', { name: 'Release to Production' }).click()
    const request = await requestPromise

    // Header calls publish() with no args -> usePublishSkill posts an empty `{}` body.
    expect(JSON.parse(request.postData() ?? '{}')).not.toHaveProperty('version')
    await expect(page.getByText(/Released to production/i)).toBeVisible({
      timeout: 5000,
    })
    await expect(page.getByText('art-999')).toBeVisible({ timeout: 5000 })
  })

  test('Release to Production network error surfaces business toast', async ({ page }) => {
    await mockPublish(
      page,
      {
        error_code: 'GITEA_503',
        http_status: 503,
        message: 'Gitea unavailable',
        details: null,
        retry_strategy: 'backoff',
      },
      503,
    )

    await enterWorkspace(page)
    await page.getByRole('button', { name: 'Release to Production' }).click()

    await expect(
      page.getByText('发版校验失败或网络异常, 当前版本仍留存在草稿区'),
    ).toBeVisible({ timeout: 5000 })
  })
})
