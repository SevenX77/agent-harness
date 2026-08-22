/** What this turn is about to carry, shown before it is sent.
 *
 * Design: `copilot-assist/mvp1-alignment.md` decision COPILOT_ASSIST-11 ⑤.
 *
 * Same reason F4 ⑤ echoes the injected context after sending: nothing rides
 * along that the user cannot see. The difference is the moment — an attachment
 * is visible BEFORE the send, while removing it is still free.
 */
import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { CopilotImageAttachment } from '../../../types/copilot'
import { decodedByteLength } from './attachment-intake'

export interface AttachmentTrayProps {
  attachments: readonly CopilotImageAttachment[]
  onRemove: (index: number) => void
}

/** Bytes as the reader counts them — never more precision than they need. */
export function formatAttachmentSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function AttachmentTray({ attachments, onRemove }: AttachmentTrayProps) {
  const { t } = useTranslation('copilot')
  if (attachments.length === 0) return null

  return (
    <ul data-attachment-tray="" className="flex flex-wrap gap-1.5 pb-1.5">
      {attachments.map((attachment, index) => (
        <li
          key={`${attachment.name ?? 'image'}-${index}`}
          data-attachment-chip={attachment.name ?? 'image'}
          className="group relative flex items-center gap-1.5 rounded-md border bg-muted/50 py-1 pl-1 pr-1.5"
        >
          <img
            src={`data:${attachment.media_type};base64,${attachment.data}`}
            alt={attachment.name ?? ''}
            className="size-8 rounded-sm object-cover"
          />
          <span className="flex flex-col leading-tight">
            <span className="max-w-[9rem] truncate text-xs text-foreground">
              {attachment.name ?? t('composer.attachments.unnamed')}
            </span>
            <span className="text-[0.7rem] text-muted-foreground">
              {formatAttachmentSize(decodedByteLength(attachment.data))}
            </span>
          </span>
          <button
            type="button"
            onClick={() => onRemove(index)}
            aria-label={t('composer.attachments.remove', { name: attachment.name ?? '' })}
            data-attachment-remove={index}
            className="ml-0.5 inline-flex size-5 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <X className="size-3" />
          </button>
        </li>
      ))}
    </ul>
  )
}
