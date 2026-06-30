import { useEffect } from 'react'

type NativeEditShortcutEvent = Pick<KeyboardEvent, 'altKey' | 'ctrlKey' | 'defaultPrevented' | 'key' | 'metaKey'>

/**
 * TEXT-SELECTION ALLOW-LIST — the single source of truth for "where native text
 * selection / double-click word-select / copy-cut-paste stays enabled".
 *
 * `useNativeDoubleClickGuard` installs an app-wide guard that disables those
 * native behaviours everywhere (the Tauri WebView2 otherwise fires stray
 * double-click + drag selections, flashing the native Edit menu / beeping).
 * Any element whose event/selection target matches a selector below is
 * AUTOMATICALLY EXCLUDED from the guard, so selecting and Ctrl/Cmd+C work there.
 *
 * There are many such read-only-but-copyable surfaces (compile errors, logs,
 * diffs, ids, file paths, model ids, …). Land in this list one of two ways:
 *   1. Be an intrinsic editable element (input / textarea / select /
 *      contenteditable / role=textbox / the Monaco editor) — handled for you.
 *   2. Mark the region with the `data-allow-text-selection` attribute — spread
 *      {@link allowTextSelectionProps} onto it.
 *
 * KEEP IN SYNC: `index.css` mirrors this list to re-enable `user-select: text`
 * (this hook handles the JS events; CSS handles the caret + visible selection).
 * When you add a selector here, add the matching rule there — search index.css
 * for `data-native-double-click-guard`.
 */
export const TEXT_SELECTION_ALLOWLIST: readonly string[] = [
  'input',
  'textarea',
  'select',
  '[contenteditable=""]',
  '[contenteditable="true"]',
  '[role="textbox"]',
  '.monaco-editor',
  '[data-allow-text-selection]',
  '[data-allow-native-double-click]', // legacy alias of data-allow-text-selection
]

/**
 * Props to spread onto any element whose text must stay natively
 * selectable/copyable despite the global guard, e.g.
 * `<pre {...allowTextSelectionProps()}>…</pre>`.
 */
export function allowTextSelectionProps() {
  return { 'data-allow-text-selection': '' } as const
}

const textSelectionAllowedSelector = TEXT_SELECTION_ALLOWLIST.join(',')

const guardedNativeEditShortcutKeys = new Set(['a', 'c', 'v', 'x'])

// `selectstart` (and selection endpoints) fire with a Text node as their target
// when the gesture begins directly ON text rather than on blank padding. A raw
// `instanceof Element` check rejects that Text node, so the guard wrongly cancels
// the selection — the app-wide symptom where you can drag-select from blank space
// but not from the text itself. Resolve any non-Element node to its parent element
// before matching the allow-list.
function resolveTargetElement(target: EventTarget | null): Element | null {
  if (target instanceof Element) return target
  if (target instanceof Node) return target.parentElement
  return null
}

export function allowsNativeDoubleClick(target: EventTarget | null) {
  const element = resolveTargetElement(target)
  return element ? Boolean(element.closest(textSelectionAllowedSelector)) : false
}

function allowsNativeSelection() {
  const selection = window.getSelection()
  return (
    allowsNativeDoubleClick(selection?.anchorNode ?? null) ||
    allowsNativeDoubleClick(selection?.focusNode ?? null)
  )
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
