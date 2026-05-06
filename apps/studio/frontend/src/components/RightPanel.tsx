import { FileText, GitCompareArrows, MessageSquare, Terminal as TerminalIcon } from 'lucide-react'
import type { CallbackEvent, CompareResult, GraphSkillDef, LintError, TerminalSession } from '../api/types'
import type { ActiveTab, ApiKeyName, ApiKeys, TerminalStatus } from '../types/studio'
import { MonacoPanel } from './MonacoPanel'
import type { EditorOnMount } from './MonacoPanel'
import { SettingsPanel } from './SettingsPanel'
import { TerminalPanel } from './TerminalPanel'
import { TracePanel } from './TracePanel'
import { DiffView } from './diff/DiffView'

interface RightPanelProps {
  activeTab: ActiveTab
  isDarkMode: boolean
  skillCode: string
  lintErrors: LintError[]
  traceLogs: CallbackEvent[]
  diffResult: CompareResult | null
  diffLoading: boolean
  diffError: string | null
  canDiffRun: boolean
  terminalSession: TerminalSession | null
  terminalStatus: TerminalStatus
  currentGraphSkill: GraphSkillDef | null
  apiKeys: ApiKeys
  onActiveTabChange: (tab: ActiveTab) => void
  onEditorMount: EditorOnMount
  onDraftChange: (code: string) => void
  onJumpToLine: (line: number | null) => void
  onCopyErrors: (message: string) => void
  onSelectPrompt: (index: number) => void
  onCompareToGolden: () => void
  onPromoteToGolden: () => void
  selectedTracePhaseId: string | null
  selectedTraceEventId: string | null
  traceLinkEnabled: boolean
  onTraceLinkEnabledChange: (enabled: boolean) => void
  onTraceEventSelect: (index: number, event: CallbackEvent) => void
  onTerminalStatusChange: (status: TerminalStatus) => void
  onApiKeyChange: (key: ApiKeyName, value: string) => void
}

export function RightPanel({
  activeTab,
  isDarkMode,
  skillCode,
  lintErrors,
  traceLogs,
  diffResult,
  diffLoading,
  diffError,
  canDiffRun,
  terminalSession,
  terminalStatus,
  currentGraphSkill,
  apiKeys,
  onActiveTabChange,
  onEditorMount,
  onDraftChange,
  onJumpToLine,
  onCopyErrors,
  onSelectPrompt,
  onCompareToGolden,
  onPromoteToGolden,
  selectedTracePhaseId,
  selectedTraceEventId,
  traceLinkEnabled,
  onTraceLinkEnabledChange,
  onTraceEventSelect,
  onTerminalStatusChange,
  onApiKeyChange,
}: RightPanelProps) {
  return (
    <div className="z-10 flex w-[520px] flex-col bg-white dark:bg-slate-900">
      <div className="flex shrink-0 border-b border-gray-200 dark:border-slate-800">
        {([
          ['code', FileText, 'SKILL.md'],
          ['trace', MessageSquare, 'Trace'],
          ['diff', GitCompareArrows, 'Diff'],
          ['terminal', TerminalIcon, 'CLI'],
        ] as const).map(([tab, Icon, label]) => (
          <button
            key={tab}
            type="button"
            className={`flex flex-1 items-center justify-center gap-2 py-3 text-sm font-medium ${
              activeTab === tab ? 'border-b-2 border-sky-600 text-sky-600 dark:text-sky-400 dark:border-sky-400' : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
            }`}
            onClick={() => onActiveTabChange(tab)}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-hidden">
        {activeTab === 'settings' ? (
          <SettingsPanel apiKeys={apiKeys} onApiKeyChange={onApiKeyChange} />
        ) : null}

        {activeTab === 'code' ? (
          <MonacoPanel
            isDarkMode={isDarkMode}
            skillCode={skillCode}
            lintErrors={lintErrors}
            onEditorMount={onEditorMount}
            onDraftChange={onDraftChange}
            onJumpToLine={onJumpToLine}
            onCopyErrors={onCopyErrors}
          />
        ) : null}

        {activeTab === 'trace' ? (
          <div className="h-full overflow-y-auto bg-slate-50 dark:bg-slate-950 p-4">
            <TracePanel
              traceLogs={traceLogs}
              activePhase={selectedTracePhaseId}
              selectedEventId={selectedTraceEventId}
              linkEnabled={traceLinkEnabled}
              onToggleLink={onTraceLinkEnabledChange}
              onSelectPrompt={onSelectPrompt}
              onSelectEvent={onTraceEventSelect}
              canCompare={canDiffRun}
              compareLoading={diffLoading}
              onCompareToGolden={onCompareToGolden}
              onPromoteToGolden={onPromoteToGolden}
            />
          </div>
        ) : null}

        {activeTab === 'diff' ? (
          <DiffView
            result={diffResult}
            loading={diffLoading}
            error={diffError}
            canCompare={canDiffRun}
            canPromote={canDiffRun}
            onCompare={onCompareToGolden}
            onPromote={onPromoteToGolden}
          />
        ) : null}

        {activeTab === 'terminal' ? (
          <TerminalPanel
            session={terminalSession}
            status={terminalStatus}
            onStatusChange={onTerminalStatusChange}
          />
        ) : null}
      </div>

      {currentGraphSkill ? (
        <div className="shrink-0 border-t border-gray-200 dark:border-slate-800 bg-gray-50 dark:bg-slate-950 px-4 py-2 text-xs text-gray-500 dark:text-gray-400">
          {currentGraphSkill.phases.length} phases / {currentGraphSkill.io.inputs.length} inputs / {currentGraphSkill.io.outputs.length} outputs
        </div>
      ) : null}
    </div>
  )
}
