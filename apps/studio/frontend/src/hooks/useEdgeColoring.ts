const EDGE_SATURATION = 70
const LIGHT_MODE_LIGHTNESS = 50
const DARK_MODE_LIGHTNESS = 65
const RESERVED_HUE_START = 220
const RESERVED_HUE_END = 270
const RESERVED_HUE_WIDTH = RESERVED_HUE_END - RESERVED_HUE_START + 1
const AVAILABLE_HUE_COUNT = 360 - RESERVED_HUE_WIDTH

const colorCache = new Map<string, string>()

function fnv1a(value: string): number {
  let hash = 0x811c9dc5
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }
  return hash >>> 0
}

function sourceHue(sourceId: string): number {
  const hue = fnv1a(sourceId) % AVAILABLE_HUE_COUNT
  return hue >= RESERVED_HUE_START ? hue + RESERVED_HUE_WIDTH : hue
}

export function getEdgeColor(sourceId: string, isDarkMode = false): string {
  const key = `${sourceId}|${isDarkMode}`
  const cached = colorCache.get(key)
  if (cached) {
    return cached
  }

  const lightness = isDarkMode ? DARK_MODE_LIGHTNESS : LIGHT_MODE_LIGHTNESS
  const color = `hsl(${sourceHue(sourceId)}, ${EDGE_SATURATION}%, ${lightness}%)`
  colorCache.set(key, color)
  return color
}
