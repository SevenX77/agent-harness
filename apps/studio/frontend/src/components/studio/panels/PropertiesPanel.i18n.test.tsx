import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it } from 'vitest'
import { PropertiesPanel } from './PropertiesPanel'
import i18n from '../../../i18n'

// Tests below switch the shared i18n singleton to exercise zh-CN rendering;
// reset it so every other test in this file (and any file run after it in the
// same worker) keeps seeing the 'en' default it was written against.
afterEach(async () => {
  await i18n.changeLanguage('en')
})

// Proves the co-located `panels` namespace (#1026 module-co-located pattern,
// this batch's first extension beyond `welcome`) is actually wired into the
// shared i18next instance via `src/i18n/namespaces.ts` — not just present as
// a JSON file nobody registered. If registration were missing or the
// namespace name were misspelled, i18next would silently fall back to
// echoing the raw key ('properties.title') instead of throwing, so asserting
// real Chinese prose (not just "not English") is the only check that would
// actually fail on a broken registration chain.
describe('PropertiesPanel speaks the reader\'s language', () => {
  it('renders the panel title and help copy in zh-CN once the language switches', async () => {
    await i18n.changeLanguage('zh-CN')

    const html = renderToStaticMarkup(<PropertiesPanel selectedNode={null} />)

    expect(html).toContain('属性')
    expect(html).toContain('属性面板来源')
    expect(html).not.toContain('>Properties<')
    expect(html).not.toContain('Properties panel source')
  })
})
