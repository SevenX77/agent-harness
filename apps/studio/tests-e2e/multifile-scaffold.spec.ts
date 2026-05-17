import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

declare global {
  interface Window {
    monaco?: {
      editor?: {
        getModels?: () => unknown[]
        getEditors: () => Array<{ getModel: () => { setValue: (value: string) => void } | null }>
      }
    }
  }
}

async function replaceActiveMonacoText(page: Page, text: string) {
  await page.locator('.monaco-editor').first().click()
  await page.waitForFunction(() => Boolean(window.monaco?.editor?.getModels?.().length))
  await page.evaluate((value) => {
    const editor = window.monaco.editor.getEditors()[0]
    editor?.getModel()?.setValue(value)
  }, text)
}

test('New Skill uses backend scaffold and saves starter files', async ({ page }) => {
  const skillId = `e2e-scaffold-${Date.now()}`
  const createResponse = page.waitForResponse((response) => (
    response.url().includes('/api/skills')
    && response.request().method() === 'POST'
    && response.status() === 201
  ))

  await page.goto('/')
  await page.getByRole('button', { name: /New Skill/i }).click()
  await page.getByRole('button', { name: 'Empty Graph' }).click()
  await page.getByRole('button', { name: /^Next$/ }).click()
  await page.getByLabel('Skill ID').fill(skillId)
  await page.getByLabel('Name').fill('E2E Scaffold')
  await page.getByLabel('Description').fill('Created by multifile scaffold e2e.')
  await page.getByRole('button', { name: /^Next$/ }).click()
  await page.getByRole('button', { name: /^Next$/ }).click()
  await page.getByLabel('Phase ID').fill('init')
  await page.getByLabel('LLM Role').fill('analyst')
  await page.getByLabel('Initial Prompt').fill('Summarize {input_text}.')
  await page.getByRole('button', { name: /^Next$/ }).click()
  await page.getByRole('button', { name: /^Create Skill$/ }).click()
  await createResponse

  await expect(page.getByText('GRAPH.md')).toBeVisible()
  await expect(page.getByText('inputs.json')).toBeVisible()
  await expect(page.getByText('outputs.json')).toBeVisible()
  await expect(page.getByText('phases')).toBeVisible()
  await expect(page.getByText('init')).toBeVisible()
  await expect(page.getByTitle('phases/init/LOGIC.md')).toBeVisible()

  await page.getByTitle('phases/init/LOGIC.md').click()
  await replaceActiveMonacoText(page, `# ${skillId}\n`)
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+S' : 'Control+S')
  await expect(page.getByText(/Saved and linted/i)).toBeVisible()
})
