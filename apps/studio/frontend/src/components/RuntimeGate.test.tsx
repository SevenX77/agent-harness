import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { RuntimeShell } from './RuntimeGate'

function render(status: 'loading' | 'ready' | 'error', message = ''): string {
  return renderToStaticMarkup(
    <RuntimeShell status={status} message={message} onRetry={() => undefined}>
      <div>app-shell-content</div>
    </RuntimeShell>,
  )
}

describe('RuntimeShell — D10 non-blocking startup gate', () => {
  it('renders the app shell when the sidecar/runtime fails (no full-screen block)', () => {
    const html = render('error', 'sidecar config unavailable')

    // The shell must remain mounted instead of being replaced by an error screen.
    expect(html).toContain('app-shell-content')
    // A non-blocking, observable degraded banner with a retry affordance.
    expect(html).toContain('Retry')
    expect(html.toLowerCase()).toContain('unavailable')
  })

  it('renders the shell while connecting (eager, no bootstrap gate)', () => {
    const html = render('loading')

    expect(html).toContain('app-shell-content')
    expect(html).toContain('Connecting')
  })

  it('renders only the shell once the runtime is ready', () => {
    const html = render('ready')

    expect(html).toContain('app-shell-content')
    expect(html).not.toContain('Retry')
    expect(html).not.toContain('Connecting')
  })
})
