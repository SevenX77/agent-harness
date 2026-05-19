import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

async function mockSkill(page: Page) {
  await page.route('**/api/skills/smoke', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        manifest: {
          schema_version: '2.0',
          type: 'graph',
          name: 'Smoke Skill',
          description: 'Copilot smoke skill',
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
      }),
    })
  })
}

async function mockCredentials(page: Page) {
  await page.route('**/api/copilot/credentials', async (route) => {
    if (route.request().method() === 'PUT') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          active_backend: 'deepseek',
          backends: {
            claude: { has_key: true },
            deepseek: { has_key: true },
            gemini: { has_key: false, V1_5_PLACEHOLDER: true },
            openai: { has_key: false, V1_5_PLACEHOLDER: true },
          },
        }),
      })
      return
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        active_backend: 'claude',
        backends: {
          claude: { has_key: true },
          deepseek: { has_key: true },
          gemini: { has_key: false, V1_5_PLACEHOLDER: true },
          openai: { has_key: false, V1_5_PLACEHOLDER: true },
        },
      }),
    })
  })
}

async function mockWebSocket(page: Page) {
  await page.addInitScript(() => {
    class MockWebSocket extends EventTarget {
      static readonly CONNECTING = 0
      static readonly OPEN = 1
      static readonly CLOSING = 2
      static readonly CLOSED = 3

      readonly url: string
      readyState = MockWebSocket.CONNECTING
      onopen: ((event: Event) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null

      constructor(url: string) {
        super()
        this.url = url
        window.setTimeout(() => {
          this.readyState = MockWebSocket.OPEN
          this.onopen?.(new Event('open'))
        }, 0)
      }

      send() {
        const events = [
          { type: 'text_delta', content: 'hello from copilot' },
          { type: 'tool_use_start', tool_name: 'Bash', tool_input: { command: 'npm test' } },
          {
            type: 'tool_use_result',
            tool_name: 'Bash',
            success: true,
            result_summary: 'diff --git a/demo.txt b/demo.txt\n--- a/demo.txt\n+++ b/demo.txt\n@@ -1 +1 @@\n-old\n+new',
          },
          { type: 'unknown_future_event', payload: { ok: true } },
          { type: 'error', message: 'Injected error for smoke' },
        ]
        events.forEach((event, index) => {
          window.setTimeout(() => {
            this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(event) }))
          }, index * 20)
        })
      }

      close() {
        this.readyState = MockWebSocket.CLOSED
        this.onclose?.(new CloseEvent('close'))
      }
    }

    Object.defineProperty(MockWebSocket, 'OPEN', { value: 1 })
    window.WebSocket = MockWebSocket as unknown as typeof WebSocket
  })
}

test.describe('Copilot V1 integration smoke', () => {
  test('covers model switching, disabled keys, tool/diff/unknown/error events, and dark mode', async ({ page }) => {
    await mockWebSocket(page)
    await mockCredentials(page)
    await mockSkill(page)

    await page.goto(`${baseURL}/#/skill/smoke/debug`)
    await expect(page.getByRole('heading', { name: 'Copilot' })).toBeVisible()
    await expect(page.getByRole('button', { name: /Gemini V1.5/i })).toBeDisabled()
    await expect(page.getByRole('button', { name: /OpenAI V1.5/i })).toBeDisabled()

    await page.locator('html').evaluate((node) => node.classList.add('dark'))
    await expect(page.locator('html')).toHaveClass(/dark/)

    await page.getByPlaceholder('Ask Copilot...').fill('inspect this skill')
    await page.getByRole('button', { name: /send/i }).click()

    await expect(page.getByText('hello from copilot')).toBeVisible()
    await expect(page.getByText('正在 Bash')).toBeVisible()
    await expect(page.getByText('Bash 完成')).toBeVisible()
    await expect(page.getByText('diff --git a/demo.txt b/demo.txt')).toBeVisible()
    await expect(page.getByText('Unknown Copilot event')).toBeVisible()
    await expect(page.getByText('Injected error for smoke')).toBeVisible()

    await page.getByRole('button', { name: 'DeepSeek' }).click()
    await expect(page.getByText('已切换模型, 聊天历史清空')).toBeVisible()
    await expect(page.getByText('hello from copilot')).toHaveCount(0)
  })
})
