import type { JsonObject } from '../api/types'

export interface InputPreset {
  id: string
  name: string
  data: JsonObject
  createdAt: string
}

function presetKey(skillId: string): string {
  return `studio:presets:${skillId}`
}

let presetIdFallbackCounter = 0

function newPresetId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  presetIdFallbackCounter += 1
  return `${Date.now()}-${presetIdFallbackCounter}`
}

export class PresetManager {
  static list(skillId: string): InputPreset[] {
    if (typeof window === 'undefined') {
      return []
    }
    try {
      const parsed: unknown = JSON.parse(localStorage.getItem(presetKey(skillId)) ?? '[]')
      if (!Array.isArray(parsed)) {
        return []
      }
      return parsed.flatMap((item) => {
        if (
          typeof item === 'object'
          && item !== null
          && 'id' in item
          && 'name' in item
          && 'data' in item
          && 'createdAt' in item
          && typeof item.id === 'string'
          && typeof item.name === 'string'
          && typeof item.createdAt === 'string'
          && typeof item.data === 'object'
          && item.data !== null
          && !Array.isArray(item.data)
        ) {
          return [item as InputPreset]
        }
        return []
      })
    } catch {
      return []
    }
  }

  static save(skillId: string, name: string, data: JsonObject): InputPreset {
    const preset: InputPreset = {
      id: newPresetId(),
      name,
      data,
      createdAt: new Date().toISOString(),
    }
    const presets = [preset, ...PresetManager.list(skillId)]
    localStorage.setItem(presetKey(skillId), JSON.stringify(presets))
    return preset
  }

  static delete(skillId: string, presetId: string): void {
    const presets = PresetManager.list(skillId).filter((preset) => preset.id !== presetId)
    localStorage.setItem(presetKey(skillId), JSON.stringify(presets))
  }

  static clear(skillId: string): void {
    localStorage.removeItem(presetKey(skillId))
  }
}
