import { lazy, Suspense, useState } from 'react'
import type { MouseEvent } from 'react'
import { ChevronDown, ChevronUp, Maximize2 } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

const MonacoEditor = lazy(async () => {
  const module = await import('@monaco-editor/react')
  return { default: module.default }
})

/**
 * 折叠属于文本自己,不属于容器(决议 2026-08-13 D3,取代 ~2KB 字节阈值)。
 *
 * 三态:收起 5 行 —— 一眼识别这段是什么;展开 20 行;看全文点链接进 Monaco
 * 只读视图。任何 trace 表面的长文本都消费这同一个原语,不允许局部自造折叠。
 */
export const FOLDED_TEXT_COLLAPSED_LINES = 5
export const FOLDED_TEXT_EXPANDED_LINES = 20

/**
 * A "line" is what the reader SEES, so a 4000-character single-line blob still
 * folds: source lines longer than this many columns count (and clip) as several
 * display lines. Without it, minified JSON would dodge the fold entirely.
 */
export const FOLDED_TEXT_WRAP_COLUMNS = 160

export interface FoldPlan {
  /** Display lines: source lines, long ones split at the wrap column. */
  lines: string[]
  /** True past 5 display lines: the text needs the fold control at all. */
  foldable: boolean
  /** True past 20 display lines: expanded is still a cut, so the full view is offered. */
  overflowsExpanded: boolean
}

/** Pure derivation of the three-state contract, pinned by tests without a DOM. */
export function foldPlan(text: string): FoldPlan {
  const lines = text.split('\n').flatMap(splitAtWrapColumn)
  return {
    lines,
    // Folding that hides a single line trades a click for nothing, so the
    // control only appears once it would hide at least two.
    foldable: lines.length > FOLDED_TEXT_COLLAPSED_LINES + 1,
    overflowsExpanded: lines.length > FOLDED_TEXT_EXPANDED_LINES,
  }
}

function splitAtWrapColumn(line: string): string[] {
  if (line.length <= FOLDED_TEXT_WRAP_COLUMNS) {
    return [line]
  }
  const pieces: string[] = []
  for (let at = 0; at < line.length; at += FOLDED_TEXT_WRAP_COLUMNS) {
    pieces.push(line.slice(at, at + FOLDED_TEXT_WRAP_COLUMNS))
  }
  return pieces
}

interface FoldedTextProps {
  text: string
  /** Names the text in the full-view dialog title and the control's aria labels. */
  label: string
  /**
   * 'end' keeps the NEWEST lines visible while collapsed — for text that is
   * still streaming, where hiding the tail would hide the very thing arriving.
   */
  clampFrom?: 'start' | 'end'
  /** Monaco language of the full view; plain text unless the caller knows better. */
  language?: string
  className?: string
}

export function FoldedText({
  text,
  label,
  clampFrom = 'start',
  language = 'plaintext',
  className,
}: FoldedTextProps) {
  const [expanded, setExpanded] = useState(false)
  const [fullViewOpen, setFullViewOpen] = useState(false)
  const plan = foldPlan(text)

  const limit = expanded ? FOLDED_TEXT_EXPANDED_LINES : FOLDED_TEXT_COLLAPSED_LINES
  const clipped = plan.lines.length > limit
  const visible = !clipped
    ? plan.lines
    : clampFrom === 'end'
      ? plan.lines.slice(plan.lines.length - limit)
      : plan.lines.slice(0, limit)

  // Rows live inside clickable surfaces; a fold toggle must not also toggle the row.
  const stop = (event: MouseEvent) => event.stopPropagation()

  return (
    <div data-slot="folded-text" className="min-w-0">
      <pre
        className={cn(
          'whitespace-pre-wrap rounded bg-background/80 p-2 text-[11px] leading-relaxed text-foreground',
          className,
        )}
      >
        {clipped && clampFrom === 'end' ? '…\n' : ''}
        {visible.join('\n')}
        {clipped && clampFrom === 'start' ? '\n…' : ''}
      </pre>
      {plan.foldable ? (
        <div className="mt-1 flex items-center gap-3">
          <button
            type="button"
            aria-label={expanded ? `Collapse ${label}` : `Expand ${label}`}
            onClick={(event) => {
              stop(event)
              setExpanded((open) => !open)
            }}
            className="inline-flex items-center gap-1 text-xs font-medium text-link hover:text-link/80"
          >
            {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            {expanded ? 'Collapse' : `Expand (${plan.lines.length} lines)`}
          </button>
          {expanded && plan.overflowsExpanded ? (
            <button
              type="button"
              aria-label={`View full ${label}`}
              onClick={(event) => {
                stop(event)
                setFullViewOpen(true)
              }}
              className="inline-flex items-center gap-1 text-xs font-medium text-link hover:text-link/80"
            >
              <Maximize2 className="h-3 w-3" />
              View full text
            </button>
          ) : null}
        </div>
      ) : null}
      {fullViewOpen ? (
        <Dialog open onOpenChange={(open) => setFullViewOpen(open)}>
          <DialogContent
            className="flex h-[80vh] flex-col sm:max-w-4xl"
            onClick={stop}
          >
            <DialogHeader>
              <DialogTitle className="text-sm">{label}</DialogTitle>
            </DialogHeader>
            <div className="min-h-0 flex-1 overflow-hidden rounded border border-border">
              <Suspense
                fallback={(
                  <div className="grid h-full place-items-center text-sm text-muted-foreground">
                    Loading editor...
                  </div>
                )}
              >
                <MonacoEditor
                  height="100%"
                  value={text}
                  language={language}
                  theme="vs-dark"
                  options={{
                    readOnly: true,
                    minimap: { enabled: false },
                    wordWrap: 'on',
                    scrollBeyondLastLine: false,
                  }}
                />
              </Suspense>
            </div>
          </DialogContent>
        </Dialog>
      ) : null}
    </div>
  )
}
