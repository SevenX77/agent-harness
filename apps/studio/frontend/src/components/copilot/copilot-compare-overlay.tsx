import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'

// F5/DEF-026: side-by-side Monaco diff ("Open Compare 并排 Monaco"). Lazy-loaded
// like LazyMonacoPanel so the heavy editor isn't in the initial bundle.
const MonacoDiffEditor = lazy(async () => {
  const module = await import('@monaco-editor/react')
  return { default: module.DiffEditor }
})

interface CopilotCompareOverlayProps {
  path: string
  before: string
  after: string
  language?: string
  onClose: () => void
}

export function CopilotCompareOverlay({
  path,
  before,
  after,
  language = 'markdown',
  onClose,
}: CopilotCompareOverlayProps) {
  const { t } = useTranslation('copilot')
  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background/95 backdrop-blur-sm">
      <header className="flex h-11 shrink-0 items-center justify-between border-b border-border px-4">
        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
          <span className="text-muted-foreground">{t('compare.title')}</span>
          <span className="font-mono">{path}</span>
          <span className="text-xs text-muted-foreground">{t('compare.direction')}</span>
        </div>
        <button
          type="button"
          aria-label={t('compare.close')}
          onClick={onClose}
          className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </header>
      <div className="min-h-0 flex-1">
        <Suspense
          fallback={
            <div className="grid h-full place-items-center text-sm text-muted-foreground">
              {t('compare.loading')}
            </div>
          }
        >
          <MonacoDiffEditor
            height="100%"
            language={language}
            original={before}
            modified={after}
            theme={
              typeof document !== 'undefined' &&
              document.documentElement.classList.contains('dark')
                ? 'vs-dark'
                : 'light'
            }
            options={{
              readOnly: true,
              renderSideBySide: true,
              minimap: { enabled: false },
              fontSize: 13,
              scrollBeyondLastLine: false,
              automaticLayout: true,
            }}
          />
        </Suspense>
      </div>
    </div>
  )
}
