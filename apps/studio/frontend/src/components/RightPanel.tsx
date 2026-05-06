import { FileText, GitCompareArrows, History, ListChecks, MessageSquare, Terminal as TerminalIcon } from 'lucide-react'
import type {
  BatchRunStatus,
  CallbackEvent,
  CompareResult,
  GraphSkillDef,
  LintError,
  RunDetail,
  TerminalSession,
  TestInputMetadata,
} from '../api/types'
import type { ActiveTab, ApiKeyName, ApiKeys, TerminalStatus, ToastKind } from '../types/studio'
import { MonacoPanel } from './MonacoPanel'
import type { EditorOnMount } from './MonacoPanel'
import { SettingsPanel } from './SettingsPanel'
import { TerminalPanel } from './TerminalPanel'
import { TracePanel } from './TracePanel'
import { DiffView } from './diff/DiffView'
import { BatchSummary } from './history/BatchSummary'
import { HistoryPanel } from './history/HistoryPanel'
import { BatchRunner } from './playground/BatchRunner'

interface RightPanelProps {
  activeTab: ActiveTab
  isDarkMode: boolean
  skillCode: string
  selectedSkillId: string | null
  lintErrors: LintError[]
  traceLogs: CallbackEvent[]
  diffResult: CompareResult | null
  diffLoading: boolean
  diffError: string | null
  canDiffRun: boolean
  batchInputs: TestInputMetadata[]
  selectedBatchInputIds: string[]
  batchStatus: BatchRunStatus | null
  batchInputsLoading: boolean
  batchRunning: boolean
  batchError: string | null
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
  onReplayRun: (detail: RunDetail) => void
  onCompareHistoryRun: (runId: string) => void
  onToggleBatchInput: (inputId: string) => void
  onRunBatch: () => void
  onRefreshBatchInputs: () => void
  onOpenBatchRun: (runId: string) => void
  selectedTracePhaseId: string | null
  selectedTraceEventId: string | null
  traceLinkEnabled: boolean
  onTraceLinkEnabledChange: (enabled: boolean) => void
  onTraceEventSelect: (index: number, event: CallbackEvent) => void
  onTerminalStatusChange: (status: TerminalStatus) => void
  onApiKeyChange: (key: ApiKeyName, value: string) => void
  pushToast: (message: string, kind?: ToastKind) => void
}

export function RightPanel({
  activeTab,
  isDarkMode,
  skillCode,
  selectedSkillId,
  lintErrors,
  traceLogs,
  diffResult,
  diffLoading,
  diffError,
  canDiffRun,
  batchInputs,
  selectedBatchInputIds,
  batchStatus,
  batchInputsLoading,
  batchRunning,
  batchError,
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
  onReplayRun,
  onCompareHistoryRun,
  onToggleBatchInput,
  onRunBatch,
  onRefreshBatchInputs,
  onOpenBatchRun,
  selectedTracePhaseId,
  selectedTraceEventId,
  traceLinkEnabled,
  onTraceLinkEnabledChange,
  onTraceEventSelect,
  onTerminalStatusChange,
  onApiKeyChange,
  pushToast,
}: RightPanelProps) {
  return (
    <div className="z-10 flex w-[520px] flex-col bg-white dark:bg-slate-900">
      <div className="flex shrink-0 border-b border-gray-200 dark:border-slate-800">
        {([
          ['code', FileText, 'SKILL.md'],
          ['trace', MessageSquare, 'Trace'],
          ['diff', GitCompareArrows, 'Diff'],
          ['history', History, 'History'],
          ['batch', ListChecks, 'Batch'],
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

        {activeTab === 'history' ? (
          <HistoryPanel
            skillId={selectedSkillId}
            onReplay={onReplayRun}
            onCompare={onCompareHistoryRun}
            pushToast={pushToast}
          />
        ) : null}

        {activeTab === 'batch' ? (
          <div className="flex h-full flex-col">
            <BatchRunner
              inputs={batchInputs}
              selectedIds={selectedBatchInputIds}
              loading={batchInputsLoading}
              running={batchRunning}
              error={batchError}
              onToggleInput={onToggleBatchInput}
              onRunBatch={onRunBatch}
              onRefresh={onRefreshBatchInputs}
            />
            <BatchSummary status={batchStatus} onOpenRun={onOpenBatchRun} />
          </div>
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
