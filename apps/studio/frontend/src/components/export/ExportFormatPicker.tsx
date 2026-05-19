import type { ExportFormat } from '../../utils/reportTemplates'

interface ExportFormatPickerProps {
  disabled?: boolean
  onSelect: (format: ExportFormat) => void
}

export function ExportFormatPicker({ disabled = false, onSelect }: ExportFormatPickerProps) {
  return (
    <div className="absolute end-0 top-full z-30 mt-1 w-44 overflow-hidden rounded-md border border-slate-200 bg-white py-1 text-sm shadow-xl dark:border-slate-800 dark:bg-slate-900">
      <button
        type="button"
        disabled={disabled}
        onClick={() => onSelect('markdown')}
        className="block w-full px-3 py-2 text-start text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 dark:text-slate-200 dark:hover:bg-slate-800"
      >
        Markdown (.md)
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onSelect('html')}
        className="block w-full px-3 py-2 text-start text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 dark:text-slate-200 dark:hover:bg-slate-800"
      >
        HTML (.html)
      </button>
    </div>
  )
}
