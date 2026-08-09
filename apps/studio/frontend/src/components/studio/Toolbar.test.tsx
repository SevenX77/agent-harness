import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { TooltipProvider } from '@/components/ui/tooltip'
import { Toolbar } from './Toolbar'

function render(settingsOpen = false): string {
  return renderToStaticMarkup(
    <TooltipProvider>
      <Toolbar
        activePanel="trace"
        onPanelChange={vi.fn()}
        settingsOpen={settingsOpen}
        onSettingsToggle={vi.fn()}
      />
    </TooltipProvider>,
  )
}

describe('Toolbar trace nav naming (decision 2026-08-09 D1)', () => {
  it('names the region after what it holds — one run\'s trace', () => {
    const html = render()
    // The label rides on the button aria-label (rendered inline, not portaled),
    // so it is observable in static markup.
    expect(html).toContain('aria-label="Trace"')
    // Retired names: the region is not a timeline, and there is no second
    // trace surface to disambiguate against.
    expect(html).not.toContain('aria-label="Timeline"')
    expect(html).not.toContain('Trace Timeline')
    expect(html).not.toContain('aria-label="Event Trace"')
  })

  it('offers no second trace surface — Full Trace is gone, not hidden', () => {
    const html = render()

    expect(html).not.toContain('Full Trace')
  })

  it('exposes the settings button as a toggle when settings are open', () => {
    const html = render(true)

    expect(html).toContain('aria-label="Settings"')
    expect(html).toMatch(/<button[^>]*aria-label="Settings"[^>]*aria-pressed="true"/)
  })
})
