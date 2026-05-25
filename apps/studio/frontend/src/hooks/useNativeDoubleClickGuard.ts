import { useEffect } from 'react'

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

function allowsNativeDoubleClick(target: EventTarget | null) {
  if (!(target instanceof Element)) return false
  return Boolean(target.closest(nativeDoubleClickAllowedSelector))
}

function shouldGuardDoubleClick(event: MouseEvent) {
  return event.button === 0 && !event.defaultPrevented && !allowsNativeDoubleClick(event.target)
}

function shouldGuardSelection(event: Event) {
  return !event.defaultPrevented && !allowsNativeDoubleClick(event.target)
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

    document.addEventListener('mousedown', handleMouseDown, true)
    document.addEventListener('dblclick', handleDoubleClick, true)
    document.addEventListener('selectstart', handleSelectStart, true)
    return () => {
      document.removeEventListener('mousedown', handleMouseDown, true)
      document.removeEventListener('dblclick', handleDoubleClick, true)
      document.removeEventListener('selectstart', handleSelectStart, true)
      delete document.documentElement.dataset.nativeDoubleClickGuard
    }
  }, [])
}
