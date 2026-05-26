import { describe, expect, it } from 'vitest'
import { nextEditableValueForPaste, shouldHandleEditablePasteShortcut } from './useEditablePasteShortcut'

describe('shouldHandleEditablePasteShortcut', () => {
  it('handles platform paste shortcuts without requiring the native macOS Edit menu', () => {
    expect(shouldHandleEditablePasteShortcut({ key: 'v', metaKey: true, ctrlKey: false, altKey: false })).toBe(true)
    expect(shouldHandleEditablePasteShortcut({ key: 'V', metaKey: false, ctrlKey: true, altKey: false })).toBe(true)
  })

  it('ignores non-paste or alternate shortcuts', () => {
    expect(shouldHandleEditablePasteShortcut({ key: 'c', metaKey: true, ctrlKey: false, altKey: false })).toBe(false)
    expect(shouldHandleEditablePasteShortcut({ key: 'v', metaKey: false, ctrlKey: false, altKey: false })).toBe(false)
    expect(shouldHandleEditablePasteShortcut({ key: 'v', metaKey: true, ctrlKey: false, altKey: true })).toBe(false)
  })
})

describe('nextEditableValueForPaste', () => {
  it('inserts clipboard text at the current cursor', () => {
    expect(nextEditableValueForPaste('sk-', 'secret', 3, 3)).toEqual({
      value: 'sk-secret',
      cursor: 9,
    })
  })

  it('replaces the selected range with clipboard text', () => {
    expect(nextEditableValueForPaste('sk-old-key', 'new', 3, 6)).toEqual({
      value: 'sk-new-key',
      cursor: 6,
    })
  })

  it('appends when the host does not expose a selection range', () => {
    expect(nextEditableValueForPaste('sk-', 'secret', null, null)).toEqual({
      value: 'sk-secret',
      cursor: 9,
    })
  })
})
