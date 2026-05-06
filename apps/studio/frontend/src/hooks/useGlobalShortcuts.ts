import { useCallback, useEffect, useRef } from 'react'
import { eventHotkey, normalizeHotkey } from '../utils/hotkeys'

export interface ShortcutContext {
  allowInInputs?: boolean
  preventDefault?: boolean
  disabled?: boolean
}

interface ShortcutBinding {
  callback: (event: KeyboardEvent) => void
  context: ShortcutContext
}

export function useGlobalShortcuts() {
  const bindingsRef = useRef(new Map<string, ShortcutBinding>())

  const register = useCallback((
    key: string,
    callback: (event: KeyboardEvent) => void,
    context: ShortcutContext = {},
  ) => {
    const normalized = normalizeHotkey(key)
    bindingsRef.current.set(normalized, {
      callback,
      context: {
        preventDefault: true,
        ...context,
      },
    })
    return () => {
      bindingsRef.current.delete(normalized)
    }
  }, [])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const binding = bindingsRef.current.get(eventHotkey(event))
      if (!binding || binding.context.disabled) {
        return
      }
      if (!binding.context.allowInInputs && isInputFocused(event.target)) {
        return
      }
      if (binding.context.preventDefault !== false) {
        event.preventDefault()
      }
      binding.callback(event)
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  return { register }
}

export function isInputFocused(target: EventTarget | null = document.activeElement): boolean {
  if (!(target instanceof HTMLElement)) {
    return false
  }
  const tagName = target.tagName.toLowerCase()
  if (['input', 'textarea', 'select'].includes(tagName)) {
    return true
  }
  if (target.isContentEditable) {
    return true
  }
  return Boolean(target.closest('.monaco-editor, .monaco-editor-background, [data-shortcut-input]'))
}
