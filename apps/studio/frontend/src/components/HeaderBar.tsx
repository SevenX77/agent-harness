import { AlertCircle, CheckCircle, FolderOpen, HardDrive, Play, Save, Terminal as TerminalIcon } from 'lucide-react'
import type { LintStatus, RunStatus } from '../types/studio'

interface HeaderBarProps {
  selectedSkillId: string | null
  inputPath: string
  outputPath: string
  pasteJson: string
  isArtifactsMenuOpen: boolean
  lintStatus: LintStatus
  runStatus: RunStatus
  onToggleArtifactsMenu: () => void
  onInputPathChange: (value: string) => void
  onOutputPathChange: (value: string) => void
  onPasteJsonChange: (value: string) => void
  onLint: () => void
  onSave: () => void
  onOpenTerminal: () => void
  onRun: () => void
}

export function HeaderBar({
  selectedSkillId,
  inputPath,
  outputPath,
  pasteJson,
  isArtifactsMenuOpen,
  lintStatus,
  runStatus,
  onToggleArtifactsMenu,
  onInputPathChange,
  onOutputPathChange,
  onPasteJsonChange,
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
          onClick={onToggleArtifactsMenu}
          className="flex items-center gap-2 rounded-md border border-indigo-200 dark:border-indigo-800 bg-indigo-50 dark:bg-indigo-900/30 px-3 py-1.5 font-medium text-indigo-700 dark:text-indigo-400 transition-colors hover:bg-indigo-100 dark:hover:bg-indigo-900/50"
        >
          <HardDrive className="h-4 w-4" />
          Artifacts
        </button>

        {isArtifactsMenuOpen ? (
          <div className="absolute left-0 top-10 z-50 w-[26rem] rounded-md border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-xl">
            <h4 className="mb-3 border-b border-gray-200 dark:border-slate-800 pb-2 font-bold text-gray-800 dark:text-gray-100">Run Input</h4>
            <div className="space-y-4">
              <label className="block">
                <span className="mb-1 block text-xs font-medium uppercase text-gray-500">Input Source</span>
                <div className="flex items-center gap-2">
                  <FolderOpen className="h-4 w-4 shrink-0 text-gray-400" />
                  <input
                    type="text"
                    value={inputPath}
                    onChange={(event) => onInputPathChange(event.target.value)}
                    className="flex-1 rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </label>

              <label className="block">
                <span className="mb-1 block text-xs font-medium uppercase text-gray-500">Output Destination</span>
                <div className="flex items-center gap-2">
                  <Save className="h-4 w-4 shrink-0 text-gray-400" />
                  <input
                    type="text"
                    value={outputPath}
                    onChange={(event) => onOutputPathChange(event.target.value)}
                    className="flex-1 rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </label>

              <label className="block">
                <span className="mb-1 block text-xs font-medium uppercase text-gray-500">Paste JSON</span>
                <textarea
                  value={pasteJson}
                  onChange={(event) => onPasteJsonChange(event.target.value)}
                  className="h-28 w-full resize-none rounded border border-gray-300 px-2 py-1.5 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder='{"chapter": "..."}'
                />
              </label>
            </div>
          </div>
        ) : null}

        <div className="flex flex-col text-xs text-gray-500">
          <span><span className="font-semibold">In:</span> {inputPath.split('/').at(-1)}</span>
          <span><span className="font-semibold">Out:</span> {outputPath.split('/').at(-1)}</span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
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
          onClick={onSave}
          disabled={!selectedSkillId || lintStatus === 'checking'}
          className="flex items-center gap-2 rounded-md border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-1.5 font-medium text-gray-700 dark:text-gray-300 transition-colors hover:bg-gray-50 dark:hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Save className="h-4 w-4" />
          Save
        </button>

        <button
          type="button"
          onClick={onOpenTerminal}
          disabled={!selectedSkillId}
          className="flex items-center gap-2 rounded-md border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/30 px-4 py-1.5 font-medium text-emerald-700 dark:text-emerald-400 transition-colors hover:bg-emerald-100 dark:hover:bg-emerald-900/50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <TerminalIcon className="h-4 w-4" />
          Open CLI
        </button>

        <button
          type="button"
          onClick={onRun}
          disabled={!selectedSkillId || runStatus === 'running'}
          className="flex items-center gap-2 rounded-md bg-sky-600 px-4 py-1.5 font-medium text-white transition-colors hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-sky-300 dark:disabled:bg-sky-900"
        >
          <Play className="h-4 w-4" />
          {runStatus === 'running' ? 'Running...' : 'Run'}
        </button>
      </div>
    </div>
  )
}
