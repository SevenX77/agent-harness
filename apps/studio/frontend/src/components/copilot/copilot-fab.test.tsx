import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { CopilotFab } from './copilot-fab'

describe('CopilotFab', () => {
  it('renders a labelled round canvas button carrying the MoirAI mark', () => {
    const html = renderToStaticMarkup(
      <CopilotFab position={null} onPositionChange={vi.fn()} panelWidth={360} onOpen={vi.fn()} />,
    )
    expect(html).toContain('aria-label="打开 MoirAI"')
    expect(html).toContain('rounded-full')
    // MoirAI constellation mark, themed on the canvas accent (no hardcoded hex).
    expect(html).toContain('<svg')
    expect(html).toContain('--studio-canvas-accent')
    expect(html).not.toMatch(/#[0-9a-fA-F]{3,6}\b/)
  })
})
