import type { MouseEvent } from 'react'
import { Maximize2 } from 'lucide-react'
import type { FileOpenRequest } from '../studio/file-types'
import { useOptionalWorkspaceContext } from '../studio/WorkspaceContext'
import { TextWell } from '../ui/text-well'
import { useTraceCopy } from './trace-copy'
import { useTraceMarkTerm } from './trace-mark-term'

/**
 * Full view opens where every other document opens — the workspace editor, as
 * a read-only virtual file (decision 2026-08-14「编辑器该怎么出现还是怎么出现」;
 * the bespoke Monaco dialog is gone). Pure so tests pin the exact payload.
 */
export function traceTextOpenRequest(label: string, text: string, language: string): FileOpenRequest {
  const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  return {
    path: `trace/${slug}.${language === 'json' ? 'json' : 'txt'}`,
    title: label,
    content: text,
    language,
    saveEnabled: false,
  }
}

/** A trace long text: the shared well, plus the editor as its full view. */
export function TraceText({
  text,
  label,
  language = 'plaintext',
  autoFollow = false,
  className,
}: {
  text: string
  /** Names the text in the editor title and the entry's aria label. */
  label: string
  language?: string
  autoFollow?: boolean
  className?: string
}) {
  const t = useTraceCopy()
  const onFileOpen = useOptionalWorkspaceContext()?.onFileOpen
  // The search matches payload VALUES, and most of them are only visible in
  // here. Marking the headline alone would leave those hits sitting on a row
  // with nothing on it to explain them — F13's own criterion for what is worse
  // than no hit at all. The well is where the reason for such a hit lives.
  const markTerm = useTraceMarkTerm()
  return (
    <TextWell
      text={text}
      markTerm={markTerm}
      autoFollow={autoFollow}
      className={className}
      overflowAction={onFileOpen ? (
        <button
          type="button"
          aria-label={t('text.viewFull', { label })}
          onClick={(event: MouseEvent) => {
            // Wells live inside clickable rows; the link must not also toggle the row.
            event.stopPropagation()
            onFileOpen(traceTextOpenRequest(label, text, language))
          }}
          className="inline-flex items-center gap-1 text-xs font-medium text-link hover:text-link/80"
        >
          <Maximize2 className="h-3 w-3" />
          {t('text.viewFullText')}
        </button>
      ) : undefined}
    />
  )
}
