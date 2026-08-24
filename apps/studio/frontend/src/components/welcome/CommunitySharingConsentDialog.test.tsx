// @vitest-environment jsdom
/**
 * First-run community-sharing consent dialog.
 *
 * Design: docs/studio/mvp1/01_workflows/00_settings.md §3.0. The dialog fires
 * once, while `AppSettings.community_sharing_choice === "unset"`, and MUST be
 * answered — no X button, no dismiss-on-outside-click, no dismiss-on-Escape —
 * because "declined" is a perfectly valid answer but "never answered, dialog
 * quietly went away" is not (that state defeats the whole point of asking).
 */

import { act, type ComponentProps } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CommunitySharingConsentDialog } from './CommunitySharingConsentDialog'

describe('CommunitySharingConsentDialog', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    document.body.innerHTML = ''
  })

  type DialogProps = ComponentProps<typeof CommunitySharingConsentDialog>

  function render(overrides: Partial<DialogProps> = {}) {
    const props: DialogProps = {
      open: true,
      onShare: vi.fn(),
      onDecline: vi.fn(),
      ...overrides,
    }
    act(() => {
      root.render(<CommunitySharingConsentDialog {...props} />)
    })
    return props
  }

  function buttonNamed(pattern: RegExp): HTMLButtonElement | undefined {
    return [...document.querySelectorAll('button')].find((button) =>
      pattern.test(button.textContent ?? ''),
    ) as HTMLButtonElement | undefined
  }

  it('does not render when the choice has already been answered (open=false)', () => {
    render({ open: false })

    expect(document.body.textContent).not.toContain('Share provider parameters with the community?')
  })

  it('renders the fixed title and body copy verbatim', () => {
    render()

    expect(document.body.textContent).toContain('Share provider parameters with the community?')
    expect(document.body.textContent).toContain(
      'Every time Studio tests a provider it learns one thing',
    )
    expect(document.body.textContent).toContain('Service address')
    expect(document.body.textContent).toContain('Your API keys')
    expect(document.body.textContent).toContain('not any fragment')
  })

  it('offers exactly two answers: turn on sharing, or not now', () => {
    render()

    expect(buttonNamed(/^Turn on sharing$/)).toBeTruthy()
    expect(buttonNamed(/^Not now$/)).toBeTruthy()
  })

  it('calls onShare only from the primary button', () => {
    const props = render()

    act(() => {
      buttonNamed(/^Turn on sharing$/)?.click()
    })

    expect(props.onShare).toHaveBeenCalledTimes(1)
    expect(props.onDecline).not.toHaveBeenCalled()
  })

  it('calls onDecline only from the secondary button', () => {
    const props = render()

    act(() => {
      buttonNamed(/^Not now$/)?.click()
    })

    expect(props.onDecline).toHaveBeenCalledTimes(1)
    expect(props.onShare).not.toHaveBeenCalled()
  })

  it('renders no close (X) button — declining is the only way to say "not now"', () => {
    render()

    expect(document.querySelector('[data-slot="dialog-close"]')).toBeNull()
  })

  it('does not close on Escape and never calls either answer callback', () => {
    const props = render()

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    })

    expect(document.body.textContent).toContain('Share provider parameters with the community?')
    expect(props.onShare).not.toHaveBeenCalled()
    expect(props.onDecline).not.toHaveBeenCalled()
  })

  it('does not close on an outside click and never calls either answer callback', () => {
    const props = render()

    act(() => {
      document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }))
      document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      document.body.dispatchEvent(new MouseEvent('pointerup', { bubbles: true }))
      document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(document.body.textContent).toContain('Share provider parameters with the community?')
    expect(props.onShare).not.toHaveBeenCalled()
    expect(props.onDecline).not.toHaveBeenCalled()
  })
})
