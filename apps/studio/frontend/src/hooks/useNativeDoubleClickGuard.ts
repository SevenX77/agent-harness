import { useEffect } from 'react'

type NativeEditShortcutEvent = Pick<KeyboardEvent, 'altKey' | 'ctrlKey' | 'defaultPrevented' | 'key' | 'metaKey'>

const nativeDoubleClickAllowedSelector = [
  'input',
  'textarea',
  'select',
  '[contenteditable=""]',
  '[contenteditable="true"]',
  '[role="textbox"]',
  '.monaco-editor',
  '[data-allow-native-double-click]',
].join(',')

const guardedNativeEditShortcutKeys = new Set(['a', 'c', 'v', 'x'])

function allowsNativeDoubleClick(target: EventTarget | null) {
  if (!(target instanceof Element)) return false
  return Boolean(target.closest(nativeDoubleClickAllowedSelector))
}

function allowsNativeSelection() {
  const selection = window.getSelection()
  return allowsNativeNode(selection?.anchorNode ?? null) || allowsNativeNode(selection?.focusNode ?? null)
}

function allowsNativeNode(node: Node | null) {
  if (!node) return false
  if (node instanceof Element) return allowsNativeDoubleClick(node)
  return allowsNativeDoubleClick(node.parentElement)
}

function shouldGuardDoubleClick(event: MouseEvent) {
  return event.button === 0 && !event.defaultPrevented && !allowsNativeDoubleClick(event.target)
}

function shouldGuardSelection(event: Event) {
  return !event.defaultPrevented && !allowsNativeDoubleClick(event.target)
}

export function shouldPreventNativeEditShortcutForTarget(
  event: NativeEditShortcutEvent,
  targetAllowsNativeEdit: boolean,
): boolean {
  if (event.defaultPrevented || targetAllowsNativeEdit) return false
  if (event.altKey || (!event.metaKey && !event.ctrlKey)) return false
  return guardedNativeEditShortcutKeys.has(event.key.toLowerCase())
}

export function shouldPreventNativeClipboardCommandForTarget(
  defaultPrevented: boolean,
  targetAllowsNativeEdit: boolean,
): boolean {
  return !defaultPrevented && !targetAllowsNativeEdit
}

export function useNativeDoubleClickGuard() {
  useEffect(() => {
    document.documentElement.dataset.nativeDoubleClickGuard = "true"

    function handleMouseDown(event: MouseEvent) {
      if (event.detail >= 2 && shouldGuardDoubleClick(event)) {
        event.preventDefault()
      }
    }

    function handleDoubleClick(event: MouseEvent) {
      if (shouldGuardDoubleClick(event)) {
        event.preventDefault()
      }
    }

    function handleSelectStart(event: Event) {
      if (shouldGuardSelection(event)) {
        event.preventDefault()
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (shouldPreventNativeEditShortcutForTarget(event, allowsNativeDoubleClick(event.target))) {
        event.preventDefault()
      }
    }

    function handleClipboardCommand(event: ClipboardEvent) {
      const targetAllowsNativeEdit = allowsNativeDoubleClick(event.target) || allowsNativeSelection()
      if (shouldPreventNativeClipboardCommandForTarget(event.defaultPrevented, targetAllowsNativeEdit)) {
        event.preventDefault()
      }
    }

    document.addEventListener('mousedown', handleMouseDown, true)
    document.addEventListener('dblclick', handleDoubleClick, true)
    document.addEventListener('selectstart', handleSelectStart, true)
    document.addEventListener('keydown', handleKeyDown, true)
    document.addEventListener('copy', handleClipboardCommand, true)
    document.addEventListener('cut', handleClipboardCommand, true)
    document.addEventListener('paste', handleClipboardCommand, true)
    return () => {
      document.removeEventListener('mousedown', handleMouseDown, true)
      document.removeEventListener('dblclick', handleDoubleClick, true)
      document.removeEventListener('selectstart', handleSelectStart, true)
      document.removeEventListener('keydown', handleKeyDown, true)
      document.removeEventListener('copy', handleClipboardCommand, true)
      document.removeEventListener('cut', handleClipboardCommand, true)
      document.removeEventListener('paste', handleClipboardCommand, true)
      delete document.documentElement.dataset.nativeDoubleClickGuard
    }
  }, [])
}
