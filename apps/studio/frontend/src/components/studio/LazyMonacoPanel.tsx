import axios from 'axios'
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { Columns2, X } from 'lucide-react'
import { toast } from 'sonner'
import { writeSkillFile } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { isTauriRuntime } from '@/config/runtime'
import { useDebouncedLint } from '@/hooks/useDebouncedLint'
import { sha256Hex } from '@/lib/hash'
import type { LintResult } from '@/api/types'
import { type EditorOnMount, type MonacoApi, type MonacoEditor as MonacoEditorInstance } from '@/components/monaco-editor-types'
import { applyLintMarkers } from '@/components/studio/lint-monaco-markers'
import { isReadOnlySkillError } from '@/components/GraphCanvas/drill-edit'

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
  workspaceRoot?: string | null
  filePath: string
  value: string
  onChange: (value: string) => void
  onSaved: (hash: string) => void
  onInFlightChange: (inFlight: boolean) => void
  onConflict: (conflict: SaveConflictPayload) => void
  language?: string
  initialHash?: string | null
  initialLintResult?: LintResult | null
  saveEnabled?: boolean
  onClose?: () => void
  onSplit?: () => void
}

export function selectEditorLintResult(
  realtimeLintResult: LintResult | null,
  initialLintResult: LintResult | null | undefined,
): LintResult | null {
  return realtimeLintResult ?? initialLintResult ?? null
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

interface SaveMonacoDraftArgs {
  skillId: string
  workspaceRoot?: string | null
  filePath: string
  content: string
  savedContent: string
  currentHash: string | null
  onSaved: (hash: string) => void
  onConflict: (conflict: SaveConflictPayload) => void
}

type SaveMonacoDraftResult =
  | { status: 'saved'; hash: string; savedContent: string }
  | { status: 'conflict' }
  | { status: 'read_only' }

export async function saveMonacoDraft({
  skillId,
  workspaceRoot,
  filePath,
  content,
  savedContent,
  currentHash,
  onSaved,
  onConflict,
}: SaveMonacoDraftArgs): Promise<SaveMonacoDraftResult> {
  const expectedHash = currentHash ?? await sha256Hex(savedContent)
  try {
    const saveTarget = isTauriRuntime() ? workspaceRoot ?? skillId : skillId
    const result = await writeSkillFile(saveTarget, filePath, content, expectedHash)
    onSaved(result.hash)
    return { status: 'saved', hash: result.hash, savedContent: content }
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
      return { status: 'conflict' }
    }
    // The backend refuses writes to a read-only skill (bundled/public, outside the
    // writable workspace) with 403 SKILL_READ_ONLY. Surface it as an explicit result
    // so the editor can flip read-only + tell the user, instead of failing silently.
    if (isReadOnlySkillError(error)) {
      return { status: 'read_only' }
    }
    throw error
  }
}

export function LazyMonacoPanel({
  title,
  skillId,
  workspaceRoot = null,
  filePath,
  value,
  onChange,
  onSaved,
  onInFlightChange,
  onConflict,
  language = 'markdown',
  initialHash = null,
  initialLintResult = null,
  saveEnabled = true,
  onClose,
  onSplit,
}: LazyMonacoPanelProps) {
  const [draft, setDraft] = useState(value)
  // Server-confirmed read-only: set when an autosave is refused with 403 SKILL_READ_ONLY
  // (a bundled/public skill outside the writable workspace). Distinct from the caller's
  // `saveEnabled` prop so a skill the frontend THOUGHT was writable still flips read-only
  // once the backend — the single source of truth for writability — refuses the write.
  const [serverReadOnly, setServerReadOnly] = useState(false)
  const serverReadOnlyRef = useRef(false)
  const draftRef = useRef(value)
  const savedRef = useRef(value)
  const hashRef = useRef<string | null>(initialHash)
  const timerRef = useRef<number | null>(null)
  const inFlightRef = useRef(false)
  const failedToastRef = useRef<string | number | null>(null)
  const flushRef = useRef<() => void>(() => undefined)
  const onChangeRef = useRef(onChange)
  const onSavedRef = useRef(onSaved)
  const onInFlightChangeRef = useRef(onInFlightChange)
  const onConflictRef = useRef(onConflict)

  useEffect(() => {
    onChangeRef.current = onChange
    onSavedRef.current = onSaved
    onInFlightChangeRef.current = onInFlightChange
    onConflictRef.current = onConflict
  })

  const lastPathRef = useRef(filePath)
  const lastHashRef = useRef(initialHash)

  useEffect(() => {
    const pathChanged = lastPathRef.current !== filePath
    const hashChanged = lastHashRef.current !== initialHash
    lastPathRef.current = filePath
    lastHashRef.current = initialHash

    if (pathChanged || hashChanged || value !== draftRef.current) {
      setDraft(value)
      draftRef.current = value
      savedRef.current = value
      hashRef.current = initialHash
      if (pathChanged) {
        // A different file may be writable even if the previous one was refused.
        serverReadOnlyRef.current = false
        setServerReadOnly(false)
      }
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current)
        timerRef.current = null
      }
      onInFlightChangeRef.current(false)
    }
  }, [filePath, initialHash, value])

  const saveNow = useCallback(async (content: string) => {
    if (!saveEnabled || content === savedRef.current) {
      return
    }
    inFlightRef.current = true
    onInFlightChangeRef.current(true)
    let attempts = 0
    while (attempts < 4) {
      try {
        const result = await saveMonacoDraft({
          skillId,
          workspaceRoot,
          filePath,
          content,
          savedContent: savedRef.current,
          currentHash: hashRef.current,
          onSaved: onSavedRef.current,
          onConflict: onConflictRef.current,
        })
        if (result.status === 'conflict') {
          return
        }
        if (result.status === 'read_only') {
          // Backend is the source of truth for writability: flip the editor read-only
          // and tell the user once (mirrors the Properties-panel read-only toast),
          // instead of silently dropping their edits.
          if (!serverReadOnlyRef.current) {
            serverReadOnlyRef.current = true
            setServerReadOnly(true)
            toast.error('This skill is read-only — fork it into your workspace to edit.')
          }
          return
        }
        hashRef.current = result.hash
        savedRef.current = result.savedContent
        if (failedToastRef.current !== null) {
          toast.dismiss(failedToastRef.current)
          failedToastRef.current = null
        }
        return
      } catch (error) {
        const status = axios.isAxiosError(error) ? error.response?.status : undefined
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
  }, [filePath, saveEnabled, skillId, workspaceRoot])

  const flush = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
    void saveNow(draftRef.current).finally(() => {
      inFlightRef.current = false
      onInFlightChangeRef.current(false)
    })
  }, [saveNow])

  useEffect(() => {
    flushRef.current = flush
  }, [flush])

  useEffect(() => () => flushRef.current(), [filePath])

  const handleChange = (nextValue: string) => {
    setDraft(nextValue)
    draftRef.current = nextValue
    onChangeRef.current(nextValue)
    if (!saveEnabled) return
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
    }
    onInFlightChangeRef.current(true)
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null
      void saveNow(draftRef.current).finally(() => {
        inFlightRef.current = false
        onInFlightChangeRef.current(false)
      })
    }, 1500)
  }

  // Realtime lint (workflow 03_compile F1): the live editor draft drives the debounced
  // /lint call; its diagnostics are the single source of truth the panel below projects.
  const { result: realtimeLintResult } = useDebouncedLint(saveEnabled ? skillId : "", draft, {
    filePath,
    workspaceRoot,
  })
  const lintResult = selectEditorLintResult(realtimeLintResult, initialLintResult)
  const editorRef = useRef<MonacoEditorInstance | null>(null)
  const monacoRef = useRef<MonacoApi | null>(null)

  const handleEditorMount = useCallback<EditorOnMount>((editor, monaco) => {
    editorRef.current = editor
    monacoRef.current = monaco
    // Paint any diagnostics the lint hook already resolved before mount (atom #6).
    applyLintMarkers(monaco, editor.getModel(), lintResult, filePath)
  }, [lintResult, filePath])

  // IDE-style inline markers (authoring N3 atom #6): project the engine's line-bearing
  // diagnostics onto the Monaco model. Pure mapping in `lint-monaco-markers`; no second
  // source of truth. Line-less diagnostics degrade to the strip above, never guess a line.
  useEffect(() => {
    applyLintMarkers(monacoRef.current, editorRef.current?.getModel() ?? null, lintResult, filePath)
  }, [lintResult, filePath])

  return (
    <section className="flex size-full min-h-0 min-w-0 flex-col bg-transparent">
      <div className="studio-canvas-panel-header flex h-10 shrink-0 items-center justify-between border-b px-3">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="font-mono text-muted-foreground">{language}</Badge>
          {onSplit ? (
            <Button
              type="button"
              onClick={onSplit}
              aria-label="Split editor"
              variant="ghost"
              size="icon"
              className="text-muted-foreground/70 hover:text-muted-foreground"
            >
              <Columns2 className="size-3.5" />
            </Button>
          ) : null}
          {onClose ? (
            <Button
              type="button"
              onClick={onClose}
              aria-label="Close editor"
              variant="ghost"
              size="icon"
              className="text-muted-foreground/70 hover:text-muted-foreground"
            >
              <X className="size-3.5" />
            </Button>
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
              readOnly: !saveEnabled || serverReadOnly,
              // Use the classic hidden <textarea> input, NOT the new EditContext API.
              // Monaco's EditContext renders the input as <div class="native-edit-context">,
              // which canvas-level key handlers (e.g. React Flow's space-to-pan, whose
              // isInputDOMNode only matches INPUT/SELECT/TEXTAREA) do NOT recognise as an
              // editable target — so they preventDefault keystrokes (Space) while you type.
              // A textarea is recognised everywhere, keeping editor input fully free.
              editContext: false,
            }}
            onMount={handleEditorMount}
            onChange={(nextValue) => handleChange(nextValue ?? '')}
          />
        </Suspense>
      </div>
    </section>
  )
}
