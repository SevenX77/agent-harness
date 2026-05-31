import { describe, expect, it } from 'vitest'
import {
  shouldPreventNativeClipboardCommandForTarget,
  shouldPreventNativeEditShortcutForTarget,
} from './useNativeDoubleClickGuard'

describe('native edit command guard', () => {
  it('prevents copy paste edit shortcuts on non-editable chrome', () => {
    expect(shouldPreventNativeEditShortcutForTarget({
      altKey: false,
      ctrlKey: false,
      defaultPrevented: false,
      key: 'c',
      metaKey: true,
    }, false)).toBe(true)
    expect(shouldPreventNativeEditShortcutForTarget({
      altKey: false,
      ctrlKey: false,
      defaultPrevented: false,
      key: 'v',
      metaKey: true,
    }, false)).toBe(true)
  })

  it('leaves edit shortcuts alone in editable targets', () => {
    expect(shouldPreventNativeEditShortcutForTarget({
      altKey: false,
      ctrlKey: false,
      defaultPrevented: false,
      key: 'c',
      metaKey: true,
    }, true)).toBe(false)
  })

  it('ignores unrelated shortcuts and already handled events', () => {
    expect(shouldPreventNativeEditShortcutForTarget({
      altKey: false,
      ctrlKey: false,
      defaultPrevented: false,
      key: 's',
      metaKey: true,
    }, false)).toBe(false)
    expect(shouldPreventNativeEditShortcutForTarget({
      altKey: false,
      ctrlKey: false,
      defaultPrevented: true,
      key: 'c',
      metaKey: true,
    }, false)).toBe(false)
  })

  it('prevents native clipboard commands only outside editable targets', () => {
    expect(shouldPreventNativeClipboardCommandForTarget(false, false)).toBe(true)
    expect(shouldPreventNativeClipboardCommandForTarget(false, true)).toBe(false)
    expect(shouldPreventNativeClipboardCommandForTarget(true, false)).toBe(false)
  })
})
