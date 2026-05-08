import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { RefObject } from 'react'
import type { MonacoApi, MonacoEditor } from '../components/MonacoPanel'
import { phaseRange, replacePhaseBlock } from '../utils/yamlAst'

interface UsePhaseSyncParams {
  markdown: string
  phaseId: string | null
  editorRef: RefObject<MonacoEditor | null>
  monacoRef: RefObject<MonacoApi | null>
  enabled: boolean
  onMarkdownChange: (markdown: string) => void
}

type DecorationCollection = ReturnType<MonacoEditor['createDecorationsCollection']>

export function usePhaseSync({
  markdown,
  phaseId,
  editorRef,
  monacoRef,
  enabled,
  onMarkdownChange,
}: UsePhaseSyncParams) {
  const [syncedBlock, setSyncedBlock] = useState<string | null>(null)
  const applyingRef = useRef(false)
  const decorationsRef = useRef<DecorationCollection | null>(null)

  const range = useMemo(() => (
    enabled && phaseId ? phaseRange(markdown, phaseId) : null
  ), [enabled, markdown, phaseId])

  useEffect(() => {
    if (!enabled || !phaseId || applyingRef.current) {
      return
    }
    const timeout = window.setTimeout(() => {
      setSyncedBlock(phaseRange(markdown, phaseId)?.yamlBlock ?? null)
    }, 150)
    return () => window.clearTimeout(timeout)
  }, [enabled, markdown, phaseId])

  useEffect(() => {
    const editor = editorRef.current
    const monaco = monacoRef.current
    decorationsRef.current?.clear()
    decorationsRef.current = null
    if (!enabled || !editor || !monaco || !range) {
      return
    }

    decorationsRef.current = editor.createDecorationsCollection([{
      range: new monaco.Range(range.startLine + 1, 1, range.endLine + 1, 1),
      options: {
        isWholeLine: true,
        className: 'phase-form-highlight',
        overviewRuler: {
          color: '#0ea5e9',
          position: monaco.editor.OverviewRulerLane.Right,
        },
      },
    }])
    editor.revealLineInCenter(range.startLine + 1)

    return () => {
      decorationsRef.current?.clear()
      decorationsRef.current = null
    }
  }, [editorRef, enabled, monacoRef, range])

  const applyPhaseBlock = useCallback((sourcePhaseId: string, yamlBlock: string) => {
    applyingRef.current = true
    const next = replacePhaseBlock(markdown, sourcePhaseId, yamlBlock)
    onMarkdownChange(next)
    window.setTimeout(() => {
      applyingRef.current = false
    }, 0)
    return next
  }, [markdown, onMarkdownChange])

  return {
    range,
    syncedBlock,
    applyPhaseBlock,
  }
}
