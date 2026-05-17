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

/*
batch-analysis phase file evidence from `find ../skills/batch-analysis/phases -maxdepth 2 -type f`:
- assemble/LOGIC.md
- continuity/SKILL.md
- entity_and_characters/SKILL.md
- parallel_analysis/SKILL.md
- prepare/LOGIC.md
*/

async function selectSkill(page: Page, skillId: string) {
  await page.getByRole('button', { name: new RegExp(`^${skillId}$`) }).click()
  await expect(page.getByRole('button', { name: /^Save$/ })).toBeEnabled()
}

async function replaceActiveMonacoText(page: Page, text: string) {
  await page.locator('.monaco-editor').first().click()
  await page.waitForFunction(() => Boolean(window.monaco?.editor?.getModels?.().length))
  await page.evaluate((value) => {
    const editor = window.monaco.editor.getEditors()[0]
    editor?.getModel()?.setValue(value)
  }, text)
}

test('batch-analysis multifile edit saves atomically and survives reload', async ({ page }) => {
  await page.goto('/')

  await selectSkill(page, 'batch-analysis')

  await expect(page.getByText('GRAPH.md')).toBeVisible()
  await expect(page.getByText('inputs.json')).toBeVisible()
  await expect(page.getByText('outputs.json')).toBeVisible()
  await expect(page.getByText('prepare')).toBeVisible()

  await page.getByText('LOGIC.md').first().click()
  const stamp = `# e2e multifile-editor ${Date.now()}`
  await replaceActiveMonacoText(page, `${stamp}\n`)

  // Ctrl+S must issue the full-file-map PUT so backend atomic write persists all files together.
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+S' : 'Control+S')
  await expect(page.getByText(/Saved and linted/i)).toBeVisible()

  await page.reload()
  await selectSkill(page, 'batch-analysis')
  await page.getByText('LOGIC.md').first().click()
  await expect(page.locator('.monaco-editor')).toContainText(stamp)
})
