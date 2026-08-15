import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { allowTextSelectionProps } from '@/hooks/useNativeDoubleClickGuard'
import { cn } from '@/lib/utils'

/**
 * The ONE long-text surface (decision 2026-08-14, superseding the 5/20-line
 * fold states): a scroll box capped at the copilot-thinking height. Short text
 * sits below the cap; long text scrolls inside the well instead of growing the
 * panel. Exactly one visual container — callers must not wrap it in another box.
 */
export function TextWell({
  text,
  autoFollow = false,
  overflowAction,
  className,
}: {
  text: string
  /** Keep the newest lines in view while the text is still streaming. */
  autoFollow?: boolean
  /** Rendered under the well once the text overflows it (e.g. a full-view link). */
  overflowAction?: ReactNode
  className?: string
}) {
  const preRef = useRef<HTMLPreElement>(null)
  const [overflowing, setOverflowing] = useState(false)
  useEffect(() => {
    const el = preRef.current
    if (!el) return
    setOverflowing(el.scrollHeight > el.clientHeight)
    if (autoFollow) {
      el.scrollTop = el.scrollHeight
    }
  }, [text, autoFollow])
  return (
    <>
      <pre
        ref={preRef}
        data-slot="text-well"
        {...allowTextSelectionProps()}
        className={cn(
          'max-h-40 min-w-0 overflow-auto whitespace-pre-wrap rounded-sm bg-muted/30 p-2 text-[11px] leading-relaxed text-foreground',
          className,
        )}
      >
        {text}
      </pre>
      {overflowing && overflowAction ? <div className="mt-1">{overflowAction}</div> : null}
    </>
  )
}
