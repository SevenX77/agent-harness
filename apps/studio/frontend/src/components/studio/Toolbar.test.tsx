import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { TooltipProvider } from '@/components/ui/tooltip'
import { Toolbar } from './Toolbar'

function render(settingsOpen = false): string {
  return renderToStaticMarkup(
    <TooltipProvider>
      <Toolbar
        activePanel="timeline"
        onPanelChange={vi.fn()}
        settingsOpen={settingsOpen}
        onSettingsToggle={vi.fn()}
      />
    </TooltipProvider>,
  )
}

describe('Toolbar trace nav naming (atom #28)', () => {
  it('labels the trace nav entry "Event Trace" instead of the ambiguous "Trace Timeline"', () => {
    const html = render()
    // The label rides on the button aria-label (rendered inline, not portaled),
    // so it is observable in static markup.
    expect(html).toContain('aria-label="Event Trace"')
    expect(html).not.toContain('Trace Timeline')
  })

  it('exposes the settings button as a toggle when settings are open', () => {
    const html = render(true)

    expect(html).toContain('aria-label="Settings"')
    expect(html).toMatch(/<button[^>]*aria-label="Settings"[^>]*aria-pressed="true"/)
  })
})
