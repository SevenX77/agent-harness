// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import {
  TEXT_SELECTION_ALLOWLIST,
  allowTextSelectionProps,
  allowsNativeDoubleClick,
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

describe('allowsNativeDoubleClick target resolution', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('allows a Text node inside an opted-in region (drag-select starting ON text)', () => {
    // The regression: a selectstart that begins directly on text fires with the
    // Text node as target; the guard must climb to its parent element so the
    // opt-in is honored, otherwise selection-from-text is wrongly cancelled.
    const region = document.createElement('div')
    region.setAttribute('data-allow-native-double-click', '')
    region.textContent = 'phases/draft/SKILL.md:12 - Unknown model alias'
    document.body.appendChild(region)
    const textNode = region.firstChild as Text

    expect(textNode.nodeType).toBe(Node.TEXT_NODE)
    expect(allowsNativeDoubleClick(textNode)).toBe(true)
    expect(allowsNativeDoubleClick(region)).toBe(true)
  })

  it('still guards a Text node outside any opted-in region', () => {
    const plain = document.createElement('div')
    plain.textContent = 'unselectable chrome'
    document.body.appendChild(plain)
    const textNode = plain.firstChild as Text

    expect(allowsNativeDoubleClick(textNode)).toBe(false)
  })

  it('returns false for a null target', () => {
    expect(allowsNativeDoubleClick(null)).toBe(false)
  })

  it('honors the semantic data-allow-text-selection opt-in (allow-list source of truth)', () => {
    const region = document.createElement('div')
    Object.entries(allowTextSelectionProps()).forEach(([k, v]) => region.setAttribute(k, v))
    region.textContent = 'copy me'
    document.body.appendChild(region)

    expect(TEXT_SELECTION_ALLOWLIST).toContain('[data-allow-text-selection]')
    expect(allowsNativeDoubleClick(region)).toBe(true)
    expect(allowsNativeDoubleClick(region.firstChild as Text)).toBe(true)
  })

  it('keeps data-allow-native-double-click working as a legacy alias', () => {
    expect(TEXT_SELECTION_ALLOWLIST).toContain('[data-allow-native-double-click]')
    const region = document.createElement('div')
    region.setAttribute('data-allow-native-double-click', '')
    document.body.appendChild(region)
    expect(allowsNativeDoubleClick(region)).toBe(true)
  })
})
