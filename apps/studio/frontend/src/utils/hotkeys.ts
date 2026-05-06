export interface NormalizedHotkey {
  key: string
  mod: boolean
  shift: boolean
  alt: boolean
}

export function normalizeHotkey(value: string): string {
  return value
    .split('+')
    .map((part) => part.trim().toLowerCase())
    .filter(Boolean)
    .sort(hotkeyPartSort)
    .join('+')
}

export function eventHotkey(event: KeyboardEvent): string {
  const parts: string[] = []
  if (event.metaKey || event.ctrlKey) {
    parts.push('mod')
  }
  if (event.shiftKey && event.key !== '?') {
    parts.push('shift')
  }
  if (event.altKey) {
    parts.push('alt')
  }
  parts.push(event.key === ' ' ? 'space' : event.key.toLowerCase())
  return normalizeHotkey(parts.join('+'))
}

export function hotkeyLabel(value: string): string {
  const isApple = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
  return normalizeHotkey(value)
    .split('+')
    .map((part) => {
      if (part === 'mod') {
        return isApple ? 'Cmd' : 'Ctrl'
      }
      if (part === 'escape') {
        return 'Esc'
      }
      if (part === 'enter') {
        return 'Enter'
      }
      return part.length === 1 ? part.toUpperCase() : part
    })
    .join(' + ')
}

function hotkeyPartSort(left: string, right: string): number {
  const order = ['mod', 'shift', 'alt']
  const leftIndex = order.indexOf(left)
  const rightIndex = order.indexOf(right)
  if (leftIndex >= 0 || rightIndex >= 0) {
    return (leftIndex >= 0 ? leftIndex : 99) - (rightIndex >= 0 ? rightIndex : 99)
  }
  return left.localeCompare(right)
}
