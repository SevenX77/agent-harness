import { describe, expect, it } from 'vitest'
import { getEdgeColor } from './useEdgeColoring'

function hslParts(color: string): { hue: number; lightness: number } {
  const match = /^hsl\((\d+), 70%, (\d+)%\)$/.exec(color)
  if (!match) {
    throw new Error(`Unexpected HSL color: ${color}`)
  }
  return {
    hue: Number(match[1]),
    lightness: Number(match[2]),
  }
}

describe('getEdgeColor', () => {
  it('returns a stable HSL color for the same source id', () => {
    expect(getEdgeColor('setup')).toBe(getEdgeColor('setup'))
  })

  it('returns different hues for different source ids', () => {
    const setup = hslParts(getEdgeColor('setup'))
    const branch = hslParts(getEdgeColor('branch'))

    expect(setup.hue).not.toBe(branch.hue)
  })

  it('uses brighter colors in dark mode', () => {
    const light = hslParts(getEdgeColor('setup', false))
    const dark = hslParts(getEdgeColor('setup', true))

    expect(light.lightness).toBe(50)
    expect(dark.lightness).toBeGreaterThanOrEqual(65)
  })
})
