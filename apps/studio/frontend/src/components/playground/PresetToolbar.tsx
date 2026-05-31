import { Save, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import type { JsonObject } from '../../api/types'
import type { ToastKind } from '../../types/studio'
import { PresetManager } from '../../utils/presets'
import type { InputPreset } from '../../utils/presets'

interface PresetToolbarProps {
  skillId: string
  values: JsonObject
  onLoad: (values: JsonObject) => void
  pushToast: (message: string, kind?: ToastKind) => void
}

export function PresetToolbar({ skillId, values, onLoad, pushToast }: PresetToolbarProps) {
  const [presets, setPresets] = useState<InputPreset[]>([])
  const [selectedId, setSelectedId] = useState('')

  const refresh = useCallback(() => {
    setPresets(PresetManager.list(skillId))
  }, [skillId])

  useEffect(() => {
    refresh()
    setSelectedId('')
  }, [skillId, refresh])

  const selectedPreset = presets.find((preset) => preset.id === selectedId)

  return (
    <div className="flex items-center gap-2">
      <select
        value={selectedId}
        onChange={(event) => {
          const preset = presets.find((item) => item.id === event.target.value)
          setSelectedId(event.target.value)
          if (preset) {
            onLoad(preset.data)
            pushToast(`Loaded preset: ${preset.name}`, 'success')
          }
        }}
        className="max-w-36 rounded-md border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 dark:border-slate-700 dark:bg-slate-800 dark:text-gray-300"
      >
        <option value="">Load preset</option>
        {presets.map((preset) => (
          <option key={preset.id} value={preset.id}>{preset.name}</option>
        ))}
      </select>
      <button
        type="button"
        onClick={() => {
          const name = prompt('Preset name:')
          if (!name?.trim()) {
            return
          }
          const preset = PresetManager.save(skillId, name.trim(), values)
          refresh()
          setSelectedId(preset.id)
          pushToast(`Saved preset: ${preset.name}`, 'success')
        }}
        className="rounded-md border border-gray-300 p-1.5 text-gray-500 hover:bg-gray-50 hover:text-gray-800 dark:border-slate-700 dark:text-gray-400 dark:hover:bg-slate-800 dark:hover:text-gray-100"
        title="Save as preset"
      >
        <Save className="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        disabled={!selectedPreset}
        onClick={() => {
          if (!selectedPreset) {
            return
          }
          PresetManager.delete(skillId, selectedPreset.id)
          refresh()
          setSelectedId('')
          pushToast(`Deleted preset: ${selectedPreset.name}`, 'success')
        }}
        className="rounded-md border border-gray-300 p-1.5 text-gray-500 hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700 dark:text-gray-400 dark:hover:bg-red-900/20 dark:hover:text-red-400"
        title="Delete preset"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}
