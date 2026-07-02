import { Save, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import type { JsonObject } from '../../api/types'
import type { ToastKind } from '../../types/studio'
import { PresetManager } from '../../utils/presets'
import type { InputPreset } from '../../utils/presets'
import { Button } from '../ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'

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
  }, [refresh])

  const selectedPreset = presets.find((item) => item.id === selectedId) ?? null

  return (
    <div className="flex items-center gap-2">
      <Select
        value={selectedId || undefined}
        onValueChange={(id) => {
          const preset = presets.find((item) => item.id === id)
          setSelectedId(id)
          if (preset) {
            onLoad(preset.data)
            pushToast(`Loaded preset: ${preset.name}`, 'success')
          }
        }}
      >
        <SelectTrigger size="sm" className="max-w-36 text-xs" aria-label="Load preset">
          <SelectValue placeholder="Load preset" />
        </SelectTrigger>
        <SelectContent>
          {presets.map((preset) => (
            <SelectItem key={preset.id} value={preset.id}>{preset.name}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="icon-sm"
            aria-label="Save as preset"
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
          >
            <Save className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Save as preset</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="icon-sm"
            disabled={!selectedPreset}
            aria-label="Delete preset"
            className="text-muted-foreground hover:text-destructive"
            onClick={() => {
              if (!selectedPreset) {
                return
              }
              PresetManager.delete(skillId, selectedPreset.id)
              refresh()
              setSelectedId('')
              pushToast(`Deleted preset: ${selectedPreset.name}`, 'success')
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Delete preset</TooltipContent>
      </Tooltip>
    </div>
  )
}
