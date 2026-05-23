import type { ExportFormat } from '../../utils/reportTemplates'
import {
  DropdownMenuContent,
  DropdownMenuItem,
} from '../ui/dropdown-menu'

interface ExportFormatPickerProps {
  disabled?: boolean
  onSelect: (format: ExportFormat) => void
}

export function ExportFormatPicker({ disabled = false, onSelect }: ExportFormatPickerProps) {
  return (
    <DropdownMenuContent align="end" className="w-44">
      <DropdownMenuItem
        disabled={disabled}
        onSelect={() => onSelect('markdown')}
      >
        Markdown (.md)
      </DropdownMenuItem>
      <DropdownMenuItem
        disabled={disabled}
        onSelect={() => onSelect('html')}
      >
        HTML (.html)
      </DropdownMenuItem>
    </DropdownMenuContent>
  )
}
