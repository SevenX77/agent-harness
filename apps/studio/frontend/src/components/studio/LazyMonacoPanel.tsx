import axios from 'axios'
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { writeSkillFile } from '@/api/client'

const MonacoEditor = lazy(async () => {
  const module = await import('@monaco-editor/react')
  return { default: module.default }
})

interface SaveConflictPayload {
  skillId: string
  path: string
  localContent: string
  remoteContent: string
  remoteHash: string | null
}

interface LazyMonacoPanelProps {
  title: string
  skillId: string
  filePath: string
  value: string
  onChange: (value: string) => void
  onSaved: (hash: string) => void
  onInFlightChange: (inFlight: boolean) => void
  onConflict: (conflict: SaveConflictPayload) => void
  language?: string
  initialHash?: string | null
  saveEnabled?: boolean
  onClose?: () => void
}

function MonacoSkeleton() {
  return (
    <div className="grid h-full place-items-center bg-muted/30 text-sm text-muted-foreground">
      Loading editor...
    </div>
  )
}

const RETRY_DELAYS = [250, 500, 1000]

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export function LazyMonacoPanel({
  title,
  skillId,
  filePath,
  value,
  onChange,
  onSaved,
  onInFlightChange,
  onConflict,
  language = 'markdown',
  initialHash = null,
  saveEnabled = true,
  onClose,
}: LazyMonacoPanelProps) {
  const [draft, setDraft] = useState(value)
  const draftRef = useRef(value)
  const savedRef = useRef(value)
  const hashRef = useRef<string | null>(initialHash)
  const timerRef = useRef<number | null>(null)
  const inFlightRef = useRef(false)
  const failedToastRef = useRef<string | number | null>(null)
  const flushRef = useRef<() => void>(() => undefined)

  useEffect(() => {
    setDraft(value)
    draftRef.current = value
    savedRef.current = value
    hashRef.current = initialHash
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
    onInFlightChange(false)
  }, [filePath, initialHash, onInFlightChange, value])

  const saveNow = useCallback(async (content: string) => {
    if (!saveEnabled || content === savedRef.current) {
      return
    }
    inFlightRef.current = true
    onInFlightChange(true)
    let attempts = 0
    while (attempts < 4) {
      try {
        const result = await writeSkillFile(skillId, filePath, content, hashRef.current)
        hashRef.current = result.hash
        savedRef.current = content
        onSaved(result.hash)
        if (failedToastRef.current !== null) {
          toast.dismiss(failedToastRef.current)
          failedToastRef.current = null
        }
        return
      } catch (error) {
        const status = axios.isAxiosError(error) ? error.response?.status : undefined
        if (status === 409 && axios.isAxiosError(error)) {
          const data = error.response?.data as {
            current_hash?: string
            current_markdown_content?: string
          }
          onConflict({
            skillId,
            path: filePath,
            localContent: content,
            remoteContent: data.current_markdown_content ?? '',
            remoteHash: data.current_hash ?? null,
          })
          return
        }
        if (status && status < 500) {
          throw error
        }
        if (attempts === 2 && failedToastRef.current === null) {
          failedToastRef.current = toast.error('Auto-save retrying')
        }
        if (attempts >= RETRY_DELAYS.length) {
          return
        }
        await wait(RETRY_DELAYS[attempts])
        attempts += 1
      }
    }
  }, [filePath, onConflict, onInFlightChange, onSaved, saveEnabled, skillId])

  const flush = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
    void saveNow(draftRef.current).finally(() => {
      inFlightRef.current = false
      onInFlightChange(false)
    })
  }, [onInFlightChange, saveNow])

  useEffect(() => {
    flushRef.current = flush
  }, [flush])

  useEffect(() => () => flushRef.current(), [filePath])

  const handleChange = (nextValue: string) => {
    setDraft(nextValue)
    draftRef.current = nextValue
    onChange(nextValue)
    if (!saveEnabled) return
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
    }
    onInFlightChange(true)
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null
      void saveNow(draftRef.current).finally(() => {
        inFlightRef.current = false
        onInFlightChange(false)
      })
    }, 1500)
  }

  return (
    <section className="flex h-full min-h-0 flex-col bg-card">
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-border px-3">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        <div className="flex items-center gap-2">
          <span className="rounded-md bg-secondary px-2 py-0.5 text-xs text-secondary-foreground">{language}</span>
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close editor"
              className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              x
            </button>
          ) : null}
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <Suspense fallback={<MonacoSkeleton />}>
          <MonacoEditor
            height="100%"
            defaultLanguage={language}
            theme={document.documentElement.classList.contains('dark') ? 'vs-dark' : 'light'}
            value={draft}
            options={{
              minimap: { enabled: false },
              fontSize: 13,
              wordWrap: 'on',
              scrollBeyondLastLine: false,
              automaticLayout: true,
              readOnly: !saveEnabled,
            }}
            onChange={(nextValue) => handleChange(nextValue ?? '')}
          />
        </Suspense>
      </div>
    </section>
  )
}
