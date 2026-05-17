import type { ReactNode } from 'react'
import { AlertCircle, CheckCircle, HardDrive, Play, Save, Terminal as TerminalIcon } from 'lucide-react'
import type { LintStatus, RunStatus } from '../types/studio'
import { DirtyIndicator } from './draft/DirtyIndicator'

interface HeaderBarProps {
  selectedSkillId: string | null
  inputSummary: string
  inputPanel: ReactNode
  canRun: boolean
  isArtifactsMenuOpen: boolean
  lintStatus: LintStatus
  runStatus: RunStatus
  dirty: boolean
  saveDisabled?: boolean
  onToggleArtifactsMenu: () => void
  onLint: () => void
  onSave: () => void
  onOpenTerminal: () => void
  onRun: () => void
}

export function HeaderBar({
  selectedSkillId,
  inputSummary,
  inputPanel,
  canRun,
  isArtifactsMenuOpen,
  lintStatus,
  runStatus,
  dirty,
  saveDisabled = false,
  onToggleArtifactsMenu,
  onLint,
  onSave,
  onOpenTerminal,
  onRun,
}: HeaderBarProps) {
  return (
    <div className="z-20 flex h-16 shrink-0 items-center justify-between border-b border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-6">
      <div className="relative flex items-center gap-5 text-sm">
        <button
          type="button"
          aria-label="Artifacts"
          onClick={onToggleArtifactsMenu}
          className="flex items-center gap-2 rounded-md border border-indigo-200 dark:border-indigo-800 bg-indigo-50 dark:bg-indigo-900/30 px-3 py-1.5 font-medium text-indigo-700 dark:text-indigo-400 transition-colors hover:bg-indigo-100 dark:hover:bg-indigo-900/50"
        >
          <HardDrive className="h-4 w-4" />
          Artifacts
        </button>

        {isArtifactsMenuOpen ? (
          <div className="absolute left-0 top-10 z-50">{inputPanel}</div>
        ) : null}

        <div className="flex flex-col text-xs text-gray-500">
          <span className="flex items-center gap-2"><DirtyIndicator dirty={dirty} /><span><span className="font-semibold">Inputs:</span> {inputSummary}</span></span>
          <span><span className="font-semibold">Mode:</span> Playground</span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Lint"
          onClick={onLint}
          disabled={!selectedSkillId || lintStatus === 'checking'}
          className="flex items-center gap-2 rounded-md border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-1.5 font-medium text-gray-700 dark:text-gray-300 transition-colors hover:bg-gray-50 dark:hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {lintStatus === 'checking' ? 'Linting...' : 'Lint'}
          {lintStatus === 'passed' ? <CheckCircle className="h-4 w-4 text-green-500" /> : null}
          {lintStatus === 'failed' ? <AlertCircle className="h-4 w-4 text-red-500" /> : null}
        </button>

        <button
          type="button"
          aria-label="Save"
          onClick={onSave}
          disabled={!selectedSkillId || lintStatus === 'checking' || saveDisabled}
          className="flex items-center gap-2 rounded-md border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-1.5 font-medium text-gray-700 dark:text-gray-300 transition-colors hover:bg-gray-50 dark:hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Save className="h-4 w-4" />
          Save
        </button>

        <button
          type="button"
          aria-label="Open CLI"
          onClick={onOpenTerminal}
          disabled={!selectedSkillId}
          className="flex items-center gap-2 rounded-md border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/30 px-4 py-1.5 font-medium text-emerald-700 dark:text-emerald-400 transition-colors hover:bg-emerald-100 dark:hover:bg-emerald-900/50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <TerminalIcon className="h-4 w-4" />
          Open CLI
        </button>

        <button
          type="button"
          aria-label="Run"
          data-testid="header-run"
          onClick={onRun}
          disabled={!selectedSkillId || !canRun || runStatus === 'running'}
          className="flex items-center gap-2 rounded-md bg-sky-600 px-4 py-1.5 font-medium text-white transition-colors hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-sky-300 dark:disabled:bg-sky-900"
        >
          <Play className="h-4 w-4" />
          {runStatus === 'running' ? 'Running...' : 'Run'}
        </button>
      </div>
    </div>
  )
}
