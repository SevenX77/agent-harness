import { Download } from 'lucide-react'
import { useState } from 'react'
import type { ExportFormat } from '../../utils/reportTemplates'
import { reportTimestamp } from '../../utils/reportTemplates'
import { ExportFormatPicker } from './ExportFormatPicker'

interface ExportButtonProps {
  label?: string
  title?: string
  filenameBase: string
  disabled?: boolean
  compact?: boolean
  buildContent: (format: ExportFormat) => Promise<string> | string
  onError?: (error: unknown) => void
}

function extensionFor(format: ExportFormat): string {
  return format === 'html' ? 'html' : 'md'
}

function mimeFor(format: ExportFormat): string {
  return format === 'html' ? 'text/html;charset=utf-8' : 'text/markdown;charset=utf-8'
}

function downloadFile(filename: string, content: string, format: ExportFormat): void {
  const blob = new Blob([content], { type: mimeFor(format) })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export function ExportButton({
  label = 'Export',
  title = 'Export report',
  filenameBase,
  disabled = false,
  compact = false,
  buildContent,
  onError,
}: ExportButtonProps) {
  const [open, setOpen] = useState(false)
  const [exporting, setExporting] = useState(false)

  const handleSelect = async (format: ExportFormat) => {
    setOpen(false)
    setExporting(true)
    try {
      const content = await buildContent(format)
      downloadFile(`${filenameBase}_${reportTimestamp()}.${extensionFor(format)}`, content, format)
    } catch (error) {
      onError?.(error)
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="relative inline-flex">
      <button
        type="button"
        disabled={disabled || exporting}
        onClick={(event) => {
          event.stopPropagation()
          setOpen((current) => !current)
        }}
        className={`inline-flex items-center gap-1.5 rounded-md border border-slate-300 font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 ${
          compact ? 'p-1.5 text-xs' : 'px-3 py-1.5 text-xs'
        }`}
        title={title}
      >
        <Download className="h-3.5 w-3.5" />
        {compact ? null : exporting ? 'Exporting...' : label}
      </button>
      {open ? (
        <ExportFormatPicker
          disabled={disabled || exporting}
          onSelect={(format) => void handleSelect(format)}
        />
      ) : null}
    </div>
  )
}

