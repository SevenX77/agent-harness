import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { TooltipProvider } from '@/components/ui/tooltip'
import { CopilotFab } from './copilot-fab'

describe('CopilotFab', () => {
  it('renders a labelled, solid circular button carrying the MoirAI mark', () => {
    const html = renderToStaticMarkup(
      <TooltipProvider>
        <CopilotFab onClick={vi.fn()} />
      </TooltipProvider>,
    )
    // A real button with an accessible name — not a bare icon on the canvas.
    expect(html).toContain('aria-label="打开 MoirAI"')
    expect(html).toContain('rounded-full')
    // The MoirAI constellation mark is inside it.
    expect(html).toContain('<svg')
  })
})
