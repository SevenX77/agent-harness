import { useEffect } from 'react'
import { isTauriRuntime } from '../config/runtime'

type PasteShortcutEvent = Pick<KeyboardEvent, 'altKey' | 'ctrlKey' | 'key' | 'metaKey'>

const editableInputTypes = new Set(['', 'email', 'password', 'search', 'tel', 'text', 'url'])

export function shouldHandleEditablePasteShortcut(event: PasteShortcutEvent): boolean {
  void event
  return false
}

export function nextEditableValueForPaste(
  currentValue: string,
  clipboardText: string,
  selectionStart: number | null,
  selectionEnd: number | null,
): { value: string; cursor: number } {
  const start = selectionStart ?? currentValue.length
  const end = selectionEnd ?? start
  const value = `${currentValue.slice(0, start)}${clipboardText}${currentValue.slice(end)}`
  return {
    value,
    cursor: start + clipboardText.length,
  }
}

export function useEditablePasteShortcut() {
  useEffect(() => {
    if (!isTauriRuntime()) return

    function handleKeyDown(event: KeyboardEvent) {
      if (event.defaultPrevented || !shouldHandleEditablePasteShortcut(event)) return
      const editable = editableTarget(event.target)
      const readText = navigator.clipboard?.readText?.bind(navigator.clipboard)
      if (!editable || !readText) return

      event.preventDefault()
      void readText()
        .then((clipboardText) => {
          if (!clipboardText) return
          pasteTextIntoEditable(editable, clipboardText)
        })
        .catch(() => undefined)
    }

    window.addEventListener('keydown', handleKeyDown, true)
    return () => window.removeEventListener('keydown', handleKeyDown, true)
  }, [])
}

function editableTarget(target: EventTarget | null): HTMLInputElement | HTMLTextAreaElement | null {
  const element = target instanceof Element
    ? target.closest('input, textarea')
    : document.activeElement
  if (element instanceof HTMLTextAreaElement) {
    return element.disabled || element.readOnly ? null : element
  }
  if (element instanceof HTMLInputElement) {
    const type = element.type.toLowerCase()
    return element.disabled || element.readOnly || !editableInputTypes.has(type) ? null : element
  }
  return null
}

function pasteTextIntoEditable(element: HTMLInputElement | HTMLTextAreaElement, clipboardText: string) {
  const next = nextEditableValueForPaste(
    element.value,
    clipboardText,
    element.selectionStart,
    element.selectionEnd,
  )
  setNativeValue(element, next.value)
  element.setSelectionRange(next.cursor, next.cursor)
  element.dispatchEvent(createPasteInputEvent(clipboardText))
}

function setNativeValue(element: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const prototype = element instanceof HTMLTextAreaElement
    ? HTMLTextAreaElement.prototype
    : HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set
  setter?.call(element, value)
}

function createPasteInputEvent(clipboardText: string): Event {
  if (typeof InputEvent !== 'undefined') {
    return new InputEvent('input', {
      bubbles: true,
      data: clipboardText,
      inputType: 'insertFromPaste',
    })
  }
  return new Event('input', { bubbles: true })
}
