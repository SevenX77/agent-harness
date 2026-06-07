import { expect, type Page, test } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

test.describe('Tauri desktop integration smoke', () => {
  test.beforeEach(async ({ page }) => {
    page.on('console', msg => console.log('PAGE LOG:', msg.text()))
  })
  test('keeps Home reachable after get_sidecar_config fails', async ({ page }) => {
    await installTauriBridge(page, { sidecarConfig: 'reject' })
    await mockSettings(page)
    await mockSkillList(page, [])

    await page.goto(baseURL)

    await expect(page.getByText('Backend startup failed')).toHaveCount(0)
    await expect(page.getByText('GSkill Studio').first()).toBeVisible()
  })

  test('opens an arbitrary folder through the native picker with a backend identity and native writer root', async ({ page }) => {
    let skillPostCount = 0
    let skillDeleteCount = 0
    let nakedAbsolutePathSkillRouteCount = 0
    let skillSummaries: unknown[] = []
    await installTauriBridge(page, {
      selectedDirectory: '/Users/sevenx/Projects/plain-folder',
    })
    await mockSettings(page)
    await page.route('**/api/skills//Users/**', async (route) => {
      nakedAbsolutePathSkillRouteCount += 1
      await route.fulfill({ status: 500, body: 'absolute paths must not be used as /skills/{skill_id}' })
    })
    await page.route('**/api/skills/plain-folder', async (route) => {
      if (route.request().method() === 'DELETE') {
        skillDeleteCount += 1
        skillSummaries = []
        await route.fulfill({ status: 204, body: '' })
        return
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify(writerSmokeDetail('plain-folder')),
      })
    })
    await page.route('**/api/skills', async (route) => {
      if (route.request().method() === 'POST') {
        skillPostCount += 1
        expect(route.request().postDataJSON()).toEqual({
          skill_id: 'plain-folder',
          directory_path: '/Users/sevenx/Projects/plain-folder',
          import_existing: true,
        })
        const summary = {
          id: 'plain-folder',
          name: 'plain-folder',
          description: 'Plain folder',
          phase_count: 1,
          has_golden: false,
          last_run_at: null,
          directory_path: '/Users/sevenx/Projects/plain-folder',
        }
        skillSummaries = [summary]
        await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(summary) })
        return
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify(skillSummaries),
      })
    })

    await page.goto(baseURL)
    const openFolder = page.getByRole('button', { name: 'Open folder' })
    await expect(openFolder).toBeVisible()
    await openFolder.click()

    await expect(page.getByText('plain-folder').first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'GRAPH.md' })).toBeVisible()
    await expect.poll(() => skillPostCount).toBe(1)
    await expect.poll(() => nakedAbsolutePathSkillRouteCount).toBe(0)
    const invokeCalls = await tauriInvokeCalls(page)
    expect(invokeCalls.some((call) => call.cmd === 'select_directory')).toBe(true)
    expect(invokeCalls.some((call) => (
      call.cmd === 'add_recent_workspace'
      && call.args
      && JSON.stringify(call.args).includes('/Users/sevenx/Projects/plain-folder')
    ))).toBe(true)

    await page.getByRole('button', { name: 'Back to Home' }).click()
    await expect(page.getByRole('button', { name: /^plain-folder/ })).toBeVisible()
    await page.locator('button[aria-label="More actions for plain-folder"]').click()
    await page.getByRole('menuitem', { name: 'Remove' }).click()
    await expect(page.getByText('Remove plain-folder from Studio?')).toBeVisible()
    await page.getByRole('button', { name: 'Remove' }).click()

    await expect.poll(() => skillDeleteCount).toBe(1)
    await expect(page.getByRole('button', { name: /^plain-folder/ })).toHaveCount(0)
    const removeCalls = await tauriInvokeCalls(page)
    expect(removeCalls.some((call) => (
      call.cmd === 'remove_recent_workspace'
      && call.args
      && JSON.stringify(call.args).includes('local:/Users/sevenx/Projects/plain-folder')
    ))).toBe(true)
  })

  test('autosaves editor changes through the native writer instead of the FastAPI file endpoint', async ({ page }) => {
    let fastapiFileWriteCount = 0
    await installTauriBridge(page)
    await mockSettings(page)
    await mockSkillList(page, [{
      id: 'writer-smoke',
      name: 'Writer Smoke',
      description: 'Native writer smoke skill',
      phase_count: 1,
      has_golden: false,
      last_run_at: null,
      directory_path: '/Users/sevenx/Projects/writer-smoke',
    }])
    await page.route(/\/api\/skills\/.*writer-smoke$/, async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify(writerSmokeDetail()),
      })
    })
    await page.route(/\/api\/skills\/.*writer-smoke\/files\//, async (route) => {
      fastapiFileWriteCount += 1
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ path: 'GRAPH.md', hash: 'python-writer-hash' }),
      })
    })

    await page.goto(baseURL)
    await page.getByRole('button', { name: /^Writer Smoke\b/ }).click()
    await page.getByRole('button', { name: 'GRAPH.md' }).click()
    await expect(page.locator('.monaco-editor')).toBeVisible({ timeout: 10000 })
    await page.locator('.monaco-editor .view-line').first().click()
    await page.waitForTimeout(500)
    await page.keyboard.type('\n# native save')
    await page.waitForTimeout(1800)

    await expect.poll(() => fastapiFileWriteCount).toBe(0)
    const nativeWrites = (await tauriInvokeCalls(page)).filter((call) => call.cmd === 'write_workspace_file')
    expect(nativeWrites.some((call) => {
      const args = call.args ?? {}
      return args.path === 'GRAPH.md' || args.relativePath === 'GRAPH.md'
    })).toBe(true)
  })

  test('does not expose retired external IDE and terminal buttons', async ({ page }) => {
    await installTauriBridge(page)
    await mockSettings(page)
    await mockSkillList(page, [{
      id: 'writer-smoke',
      name: 'Writer Smoke',
      description: 'Native writer smoke skill',
      phase_count: 1,
      has_golden: false,
      last_run_at: null,
      directory_path: '/Users/sevenx/Projects/writer-smoke',
    }])
    await page.route(/\/api\/skills\/.*writer-smoke$/, async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify(writerSmokeDetail()),
      })
    })

    await page.goto(baseURL)
    await page.getByRole('button', { name: /^Writer Smoke\b/ }).click()

    await expect(page.getByRole('button', { name: 'Open in Cursor' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Open in Terminal' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Open in Codex' })).toHaveCount(0)
  })
})

async function installTauriBridge(
  page: Page,
  options: {
    sidecarConfig?: 'ready' | 'reject'
    selectedDirectory?: string
  } = {},
) {
  await page.addInitScript((bridgeOptions) => {
    type InvokeCall = { cmd: string; args: Record<string, unknown> | null }
    const calls: InvokeCall[] = []
    Object.defineProperty(window, '__TAURI_INVOKE_CALLS__', {
      value: calls,
      configurable: true,
    })
    Object.defineProperty(window, '__TAURI_INTERNALS__', {
      value: {
        invoke: async (cmd: string, args: Record<string, unknown> | null = null) => {
          calls.push({ cmd, args })
          if (cmd === 'get_sidecar_config') {
            if (bridgeOptions.sidecarConfig === 'reject') {
              throw new Error('Python sidecar disabled')
            }
            return {
              port: Number(window.location.port || 80),
              baseURL: `${window.location.origin}/api`,
              wsURL: `${window.location.origin.replace(/^http/, 'ws')}/ws`,
              resourceDir: '/workspace/studio-resources',
              configDir: '/workspace/studio-config',
              api_token: null,
            }
          }
          if (cmd === 'select_directory') {
            return bridgeOptions.selectedDirectory ?? '/Users/sevenx/Projects/writer-smoke'
          }
          if (cmd === 'write_workspace_file') {
            const path = String(args?.path ?? args?.relativePath ?? '')
            return { path, hash: 'native-writer-hash' }
          }
          if (cmd === 'add_recent_workspace') {
            return null
          }
          if (cmd === 'reveal_in_file_manager') {
            return null
          }
          return null
        },
        transformCallback: () => 1,
        unregisterCallback: () => undefined,
      },
      configurable: true,
    })
  }, {
    sidecarConfig: options.sidecarConfig ?? 'ready',
    selectedDirectory: options.selectedDirectory ?? null,
  })
}

async function tauriInvokeCalls(page: Page): Promise<Array<{ cmd: string; args?: Record<string, unknown> }>> {
  return page.evaluate(() => (
    ((window as unknown as { __TAURI_INVOKE_CALLS__?: Array<{ cmd: string; args?: Record<string, unknown> }> })
      .__TAURI_INVOKE_CALLS__) ?? []
  ))
}

async function mockSettings(page: Page) {
  await page.route('**/api/settings', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        user_id: '',
        gitea_host: '',
        default_skills_directory: '',
      }),
    })
  })
}

async function mockSkillList(page: Page, skills: unknown[]) {
  await page.route('**/api/skills', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(skills),
    })
  })
}

function writerSmokeDetail(skillId = 'writer-smoke') {
  return {
    manifest: {
      schema_version: 'v0.3.0',
      name: skillId,
      description: 'Native writer smoke skill',
      io: {
        inputs: { type: 'object', properties: {} },
        outputs: { type: 'object', properties: {} },
      },
      phases: ['draft'],
    },
    graph_topology: [
      { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'skill' },
    ],
    node_schema_v21: {},
    io_schema: {},
    file_paths: {},
    files: {
      'GRAPH.md': [
        '---',
        'schema_version: "v0.3.0"',
        `name: ${skillId}`,
        'phases:',
        '  - draft',
        '---',
        '<phase depends_on="input" output>draft</phase>',
        '',
      ].join('\n'),
      'phases/draft/SKILL.md': [
        '---',
        'name: draft',
        'mode: skill',
        'tools: []',
        '---',
        '<system_prompt>',
        'Draft.',
        '</system_prompt>',
        '<exit_contract>',
        'Finish.',
        '</exit_contract>',
        '',
      ].join('\n'),
    },
    manifest_errors: null,
    has_golden: false,
    latest_run_metadata: null,
    lint_result: null,
  }
}
