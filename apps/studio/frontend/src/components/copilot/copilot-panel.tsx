import React, { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import { ArrowUp, ChevronDown, CircleAlert, Loader2, MonitorCheck, Square, SquareTerminal } from 'lucide-react'
import { allowTextSelectionProps } from '@/hooks/useNativeDoubleClickGuard'
import { toast } from 'sonner'
import { prepareCopilotJudgeContext, type CopilotJudgeResponse } from '../../api/client'
import { getRegistry, getRoles, putRoles, type RegistryResponse, type RolesData } from '../../api/llm'
import type { CopilotController, CopilotJudgeContext } from '../../hooks/useCopilot'
import { resolveCopilotSendRole } from '../studio/settings/copilot/copilot-role-derivation'
import { useStudioEventStream } from '../../hooks/useStudioEventStream'
import { useTemplates } from '../../hooks/useTemplates'
import type { CopilotMessage } from '../../types/copilot'
import {
  closeCodeAssistant,
  ensureCodeAssistantStatusEvents,
  subscribeCodeAssistantStatus,
  unobservedCodeAssistantStatus,
  type AssistantState,
  type CodeAssistantStatus,
} from '../../lib/tauri'
import { Button } from '../ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
import { Bubble, BubbleContent } from '../ui/bubble'
import { Message, MessageContent } from '../ui/message'
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from '../ui/message-scroller'
import { BACKEND_UNAVAILABLE_MESSAGE, errorMessage } from '@/utils/errors'
import { AnalysisBar } from './analysis-bar'
import { MoiraiMark } from './moirai-mark'
import { ToolApprovalCard } from './tool-approval-card'
import { DiffBubble } from './diff-bubble'
import { ModelPicker } from './model-picker'
import { PatchProposedBubble, type CopilotFileAction } from './patch-proposed-bubble'
import { RolePicker, copilotRoleOptions } from './role-picker'
import { startCliTerminalSession, type CliTerminalSession } from './cli-terminal-session'
import { SessionTabs } from './session-tabs'
import { ToolCallBubble } from './tool-call-bubble'
import { cn } from '@/lib/utils'
import { formatProcessedDuration, buildAssistantView, type TranscriptSegment } from './transcript'

interface ChatMessageItemProps {
  message: CopilotMessage
  skillId: string | null
  workspaceRoot?: string | null
  onFileChanged?: (path: string, action: CopilotFileAction) => void
}

function ChatMessageItemBase({ message, skillId, workspaceRoot, onFileChanged }: ChatMessageItemProps) {
  const isUser = message.role === 'user'
  if (isUser) {
    // chat.md contract: the colored message surface is Bubble, never a styled
    // div with bg-muted and hand-managed corners.
    return (
      <Message align="end" data-copilot-message-role="user">
        <MessageContent>
          <Bubble variant="muted" align="end" className="text-sm">
            <BubbleContent>{message.content}</BubbleContent>
          </Bubble>
        </MessageContent>
      </Message>
    )
  }
  const view = buildAssistantView(message)
  const streaming = message.status === 'running'
  // F6-7/F8: the wait shimmer covers everything up to the first VISIBLE
  // activity — the first thinking or answer token. context_resolved / tool
  // events alone don't clear it; once thinking streams, the live transcript
  // takes over as the waiting indicator.
  const waiting =
    streaming && !message.content && !message.events.some((event) => event.type === 'thinking_delta')
  const ctx: ProcessRenderContext = { streaming, skillId, workspaceRoot, onFileChanged }

  const renderSegmentNode = (segment: TranscriptSegment, isFinalAnswer: boolean) => {
    if (segment.kind === 'text') {
      return (
        <div
          key={segment.id}
          className={cn(
            "copilot-prose leading-relaxed",
            isFinalAnswer 
              ? "text-[13px] text-foreground font-normal"
              : "text-xs text-muted-foreground font-normal"
          )}
        >
          <ReactMarkdown>{segment.content}</ReactMarkdown>
        </div>
      )
    }
    return renderProcessSegment(segment, ctx)
  }

  return (
    // R7-A: chat content is selectable (PM「聊天内容无法选择」) — opt into the
    // global text-selection allowlist (FRONTEND_UI_SPEC §2.11).
    <Message align="start" data-copilot-message-role="assistant" {...allowTextSelectionProps()}>
      <MessageContent>
        {waiting ? <ThinkingRow /> : null}
        <div className="space-y-1.5">
          {streaming ? (
            // Live: the process streams inline in natural chronological order
            view.segments.map((segment, index) =>
              renderSegmentNode(segment, index === view.lastTextIndex)
            )
          ) : (
            // Settled: process folds into details, final answer stays expanded
            <>
              {view.segments.some((_, index) => index !== view.lastTextIndex) && (
                <details className="text-xs text-muted-foreground group">
                  <summary className="flex cursor-pointer select-none items-center gap-1 font-medium text-muted-foreground transition-colors hover:text-foreground">
                    <span className="transition-transform group-open:rotate-90">›</span>
                    Processed{view.durationMs != null ? ` ${formatProcessedDuration(view.durationMs)}` : ''}
                  </summary>
                  <div className="mt-1 space-y-1.5 pl-2">
                    {view.segments
                      .map((segment, index) => ({ segment, index }))
                      .filter(({ index }) => index !== view.lastTextIndex)
                      .map(({ segment }) => renderSegmentNode(segment, false))
                    }
                  </div>
                </details>
              )}
              {view.lastTextIndex >= 0 && (
                renderSegmentNode(view.segments[view.lastTextIndex], true)
              )}
            </>
          )}
        </div>
      </MessageContent>
    </Message>
  )
}

/** Shared context for rendering one process segment (live or inside the fold). */
interface ProcessRenderContext {
  streaming: boolean
  skillId: string | null
  workspaceRoot?: string | null
  onFileChanged?: (path: string, action: CopilotFileAction) => void
}

/**
 * R7-A: render one PROCESS segment (thinking / tool / context / intermediate
 * narration). No left rule anywhere (PM「去掉对话小字前面的那根竖线」); tool
 * spinners stop once the turn settles (see ToolCallBubble `streaming`).
 */
function renderProcessSegment(segment: TranscriptSegment, ctx: ProcessRenderContext): ReactNode {
  if (segment.kind === 'text') {
    // Intermediate narration before the final answer — dim, one size down.
    return (
      <div key={segment.id} className="copilot-prose text-xs leading-relaxed text-muted-foreground">
        <ReactMarkdown>{segment.content}</ReactMarkdown>
      </div>
    )
  }
  if (segment.kind === 'thinking') {
    return <ThinkingBlock key={segment.id} content={segment.content} streaming={ctx.streaming} />
  }
  const event = segment.event
  if (event.type === 'tool_use_start') {
    return <ToolCallBubble key={event.id} event={event} streaming={ctx.streaming} />
  }
  if (event.type === 'tool_use_result') {
    return (
      <div key={event.id}>
        <ToolCallBubble event={event} streaming={ctx.streaming} />
        <DiffBubble event={event} />
      </div>
    )
  }
  if (event.type === 'error') {
    return (
      <div key={event.id} className="py-0.5 text-xs text-destructive">
        <div className="flex items-center gap-2 font-medium">
          <CircleAlert className="size-3.5" />
          Copilot error
        </div>
        <p className="mt-1 whitespace-pre-wrap leading-snug">{event.message}</p>
      </div>
    )
  }
  if (event.type === 'patch_proposed') {
    return (
      <PatchProposedBubble
        key={event.id}
        event={event}
        skillId={ctx.skillId}
        workspaceRoot={ctx.workspaceRoot}
        onFileChanged={ctx.onFileChanged}
      />
    )
  }
  if (event.type === 'tool_approval_required') {
    return <ToolApprovalCard key={event.id} event={event} skillId={ctx.skillId} />
  }
  if (event.type === 'context_resolved') {
    return (
      <details key={event.id} className="py-0.5 text-xs text-muted-foreground">
        <summary className="cursor-pointer font-medium text-muted-foreground transition-colors hover:text-foreground">{event.summary}</summary>
        <pre className="mt-1.5 max-h-48 overflow-auto whitespace-pre-wrap rounded-sm bg-muted/30 p-2 leading-snug">
          {event.detail}
        </pre>
      </details>
    )
  }
  if (event.type === 'unknown') {
    return (
      <details key={event.id} className="py-0.5 text-xs text-muted-foreground">
        <summary className="cursor-pointer font-medium text-muted-foreground transition-colors hover:text-foreground">Unknown Copilot event</summary>
        <pre className="mt-1.5 max-h-48 overflow-auto whitespace-pre-wrap rounded-sm bg-muted/30 p-2 leading-snug">
          {JSON.stringify(event.payload, null, 2)}
        </pre>
      </details>
    )
  }
  return null
}

/**
 * R7-A: reasoning trace. While the turn streams the block stays open and its
 * scroll box auto-follows the newest reasoning (PM「thinking 的内容也不会自动
 * 往下滚动」). Once settled it lives inside the folded process row.
 */
function ThinkingBlock({ content, streaming }: { content: string; streaming: boolean }) {
  const preRef = useRef<HTMLPreElement>(null)
  useEffect(() => {
    if (streaming && preRef.current) {
      preRef.current.scrollTop = preRef.current.scrollHeight
    }
  }, [content, streaming])
  return (
    <details open={streaming} className="py-0.5 text-xs text-muted-foreground">
      <summary className="cursor-pointer font-medium text-muted-foreground transition-colors hover:text-foreground">Thought</summary>
      <pre
        ref={preRef}
        {...allowTextSelectionProps()}
        className="mt-1.5 max-h-40 overflow-auto whitespace-pre-wrap rounded-sm bg-muted/30 p-2 leading-snug"
      >
        {content}
      </pre>
    </details>
  )
}

export const ChatMessageItem = React.memo(ChatMessageItemBase)

/** F6 R3/R4: visible wait for the first answer token (cold spawns take 10-30s).
 * shadcn `shimmer` utility — the official loading-text treatment. */
function ThinkingRow() {
  return (
    <div className="py-1 text-sm text-muted-foreground" data-copilot-thinking="true">
      <span className="shimmer">Thinking…</span>
    </div>
  )
}

interface CopilotPanelProps {
  skillId: string | null
  workspaceRoot?: string | null
  copilot: CopilotController
  view?: 'edit' | 'eval'
  judgeRefs?: {
    runResultsRef: string
    baselineRef: string
  } | null
  // F7: id of the run that just finished (predict/run) — drives the analysis bar.
  completedRunId?: string | null
  onJudgePrepared?: (refs: CopilotJudgeResponse) => void
  // F5/DEF-025: a copilot edit hit disk — reload the editor buffer + recompile.
  onFileChanged?: (path: string, action: CopilotFileAction) => void
  // R5-E: collapse the panel back to the canvas MoirAI FAB (header control).
  onCollapse?: () => void
  // The CLI session belongs to the WORKSPACE, not to this panel: collapsing the
  // panel unmounts it, and a session owned here would die with it (design
  // ah-orchestration-design.md §10 D3 — collapsing is a detach, not a shutdown).
  cliSession?: CliTerminalSession | null
  onCliSessionChange?: (session: CliTerminalSession | null) => void
}

/** F6: Enter sends, Shift+Enter breaks the line, and an IME composition never sends. */
export function isComposerSendKey(event: {
  key: string
  shiftKey: boolean
  nativeEvent: { isComposing: boolean }
}): boolean {
  return event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing
}

export function copilotBackendErrorMessage(error: unknown, fallback: string): string {
  return errorMessage(error) === BACKEND_UNAVAILABLE_MESSAGE
    ? 'Copilot backend unavailable'
    : fallback
}

interface DraftJudgeContextScope {
  skillId: string | null
  view: 'edit' | 'eval'
  judgeRefs: {
    runResultsRef: string
    baselineRef: string
  } | null
}

type CodeAssistantId = 'claude' | 'codex'

// 状态一律是 AssistantState 对象。这里曾经还接受 boolean / null / undefined 并把它们
// 折成 'inactive'——那条兼容分支自 task 8 起就是死路径(Rust 侧只发 AssistantState),
// 而 `?? 'inactive'` 本身就是"未知冒充没在跑"这个缺陷在前端的复制品,已随决议
// 2026-08-03 D-C6 一起删除。
//
// The code-assistant phase contract (tauri.ts AssistantState:
// unknown | inactive | starting | active | lingering | degraded | error) decides which
// header control the panel projects — not a bare inactive-vs-not binary. Only a genuinely
// running assistant exposes the Attach/Close management control; 'error' keeps its
// pre-existing running-control mapping (unchanged, out of task-9 scope), while
// 'starting' (mid-transition, hands-off), 'unknown' (尚未观测, hands-off) and
// 'degraded' (recoverable → Open) are not attachable and route to the Open control instead.
function isAssistantActive(state: AssistantState): boolean {
  switch (state.status) {
    case 'active':
    case 'error':
      return true
    case 'unknown':
    case 'inactive':
    case 'starting':
    case 'lingering':
    case 'degraded':
      return false
    default:
      return false
  }
}

// lingering = ah 的运行时仍在（ahd 存活 ⇒ tmux 及其 remain-on-exit 死窗格没被回收），但里面
// 已经没有活的 CLI 会话。它不是 active（attach 上去就是那块死窗格），也不能算 inactive
// （那会让面板谎称什么都没在跑、把用户导回 Open）——它自己是一类：只能 Close。
function isAssistantLingering(state: AssistantState): boolean {
  return state.status === 'lingering'
}

// 两个 hands-off 相位各自的进行态文案。它们不是"功能不可用",而是"正在发生的事还没有
// 结论",所以头部渲染的是一个**带 spinner 的进行态控件**,而不是一个外观与不可用无异的
// 禁用按钮——后者会被读成"坏了",于是被反复点击(FRONTEND_UI_SPEC §2「进行态 vs 不可用」)。
//
// starting = CLI 已经拉起但还没就绪;unknown = Studio 还没拿到任何一帧快照
// (决议 2026-08-03 D-C3)。`starting` 是更具体的事实,同时出现时它优先。
export function codeAssistantPendingLabel(status: CodeAssistantStatus): string | null {
  if (status.claude.status === 'starting' || status.codex.status === 'starting') {
    return 'Starting…'
  }
  if (status.claude.status === 'unknown' || status.codex.status === 'unknown') {
    return 'Checking…'
  }
  return null
}

function isAssistantReadOnly(state: AssistantState): boolean {
  return state.readOnly
}

// 需要收尾的助手 = 真正在跑的 + 只剩残留运行时的。前者靠 Close 停掉会话，后者靠 Close 让
// ah 回收 tmux；两者都必须让头部停在管理控件上，不能回落成 `Open in CLI`。
export function closableCodeAssistantIds(status: CodeAssistantStatus): CodeAssistantId[] {
  return [
    ...(isAssistantActive(status.claude) || isAssistantLingering(status.claude) ? (['claude'] as const) : []),
    ...(isAssistantActive(status.codex) || isAssistantLingering(status.codex) ? (['codex'] as const) : []),
  ]
}

export function codeAssistantCloseButtonLabel(status: CodeAssistantStatus): string | null {
  const closable = closableCodeAssistantIds(status)
  if (closable.length === 0) {
    return null
  }
  if (closable.every(id => isAssistantReadOnly(status[id]))) {
    return 'Detach'
  }
  if (closable.length > 1) {
    return 'Close assistants'
  }
  return closable[0] === 'claude' ? 'Close Claude code' : 'Close Codex'
}

function codeAssistantLabel(assistant: CodeAssistantId): string {
  return assistant === 'claude' ? 'Claude code' : 'Codex'
}

// Attach 覆盖的集合与 Close 相同：有运行时就既能看它、也能关它（PM 裁决 2026-08-04，
// 取代 D-A3「lingering 可 Close 不可 Attach」）。ah 有意用 `remain-on-exit` 把死窗格
// 留着供事后取证，那一屏正是使用者想看的——CLI 怎么退的、最后报了什么。
//
// 但残留的入口必须**说明它是已退出的会话**：不标出来，点下去看到一块冻住的窗格会被读成
// 卡死。销毁那块窗格只能由 Close 显式发起，attach 不碰它。
export function codeAssistantAttachMenuLabels(status: CodeAssistantStatus): string[] {
  return closableCodeAssistantIds(status).map((assistant) =>
    isAssistantLingering(status[assistant])
      ? `Attach ${codeAssistantLabel(assistant)} (exited)`
      : `Attach ${codeAssistantLabel(assistant)}`,
  )
}

function judgeContextMatchesScope(context: CopilotJudgeContext, scope?: DraftJudgeContextScope): boolean {
  if (!scope) {
    return true
  }
  if (!scope.skillId || scope.view !== 'eval' || !scope.judgeRefs) {
    return false
  }
  const skillPrefix = `${scope.skillId}/`
  return (
    context.baseline_ref === scope.judgeRefs.baselineRef
    && context.diff_summary.run_results_ref === scope.judgeRefs.runResultsRef
    && context.compare_result_ref.startsWith(skillPrefix)
    && context.judge_context_ref.startsWith(skillPrefix)
    && context.baseline_ref.startsWith(skillPrefix)
    && context.diff_summary.run_results_ref.startsWith(skillPrefix)
  )
}

export function nextDraftJudgeContext(
  nextDraft: string,
  context: CopilotJudgeContext | null,
  scope?: DraftJudgeContextScope,
): CopilotJudgeContext | null {
  if (!context) {
    return null
  }
  return nextDraft === buildCopilotJudgeDraft(context) && judgeContextMatchesScope(context, scope) ? context : null
}

const CliTerminalView = lazy(() =>
  import('./cli-terminal-view').then((module) => ({ default: module.CliTerminalView })),
)

export function CopilotPanel({
  skillId,
  workspaceRoot,
  copilot,
  view = 'edit',
  judgeRefs = null,
  completedRunId = null,
  onJudgePrepared,
  onFileChanged,
  onCollapse,
  cliSession = null,
  onCliSessionChange,
}: CopilotPanelProps) {
  const [draft, setDraft] = useState('')
  const [dismissedRunId, setDismissedRunId] = useState<string | null>(null)
  const [registry, setRegistry] = useState<RegistryResponse | null>(null)
  const [selectedRouteId, setSelectedRouteId] = useState('')
  const [rolesData, setRolesData] = useState<RolesData | null>(null)
  // R5-C: the role/route slot shows a skeleton until BOTH config fetches settle
  // (registry can take ~45s on cold probe). Settled = resolved OR failed — a
  // failed fetch must drop the skeleton (picker hides as before), never park it.
  const [registrySettled, setRegistrySettled] = useState(false)
  const [rolesSettled, setRolesSettled] = useState(false)
  const [selectedRole, setSelectedRole] = useState('')
  const [draftJudgeContext, setDraftJudgeContext] = useState<CopilotJudgeContext | null>(null)
  const [closingCodeAssistant, setClosingCodeAssistant] = useState(false)
  const [codeAssistantStatus, setCodeAssistantStatus] = useState<CodeAssistantStatus>(unobservedCodeAssistantStatus())
  const shouldLoadTemplates = !skillId && copilot.messages.length === 0
  const { templates, templatesLoading } = useTemplates({ enabled: shouldLoadTemplates })
  const inEvalView = view === 'eval'
  const roleOptions = useMemo(
    () => copilotRoleOptions(rolesData, registry?.model_groups ?? []),
    [rolesData, registry],
  )
  const codeAssistantWorkspace = workspaceRoot?.trim() || null

  async function askCopilotJudge() {
    if (!skillId || !judgeRefs) {
      return
    }
    try {
      const refs = await prepareCopilotJudgeContext(skillId, judgeRefs)
      setDraft(buildCopilotJudgeDraft(refs))
      setDraftJudgeContext(refs)
      onJudgePrepared?.(refs)
    } catch (error) {
      toast.error(copilotBackendErrorMessage(error, 'Copilot Judge context unavailable'))
    }
  }

  function handleJudgePrepared(refs: CopilotJudgeResponse) {
    setDraft(buildCopilotJudgeDraft(refs))
    setDraftJudgeContext(refs)
    onJudgePrepared?.(refs)
  }

  useEffect(() => {
    setDraftJudgeContext((current) => nextDraftJudgeContext(draft, current, { skillId, view, judgeRefs }))
  }, [draft, skillId, view, judgeRefs])

  const refreshRegistry = useCallback((options: { force?: boolean } = {}) => {
    getRegistry(options)
      .then((nextRegistry) => {
        setRegistry(nextRegistry)
      })
      .catch((error) => {
        toast.error(copilotBackendErrorMessage(error, 'Copilot route config unavailable'))
      })
  }, [])

  const refreshRoles = useCallback((options: { force?: boolean } = {}) => {
    getRoles(options)
      .then((nextRoles) => {
        setRolesData(nextRoles)
      })
      .catch((error) => {
        toast.error(copilotBackendErrorMessage(error, 'Copilot roles unavailable'))
      })
  }, [])

  useStudioEventStream({
    onRegistryChanged: () => refreshRegistry({ force: true }),
    onRolesChanged: () => refreshRoles({ force: true }),
  })

  useEffect(() => {
    let cancelled = false
    getRegistry()
      .then((nextRegistry) => {
        if (cancelled) {
          return
        }
        setRegistry(nextRegistry)
      })
      .catch((error) => {
        toast.error(copilotBackendErrorMessage(error, 'Copilot route config unavailable'))
      })
      .finally(() => {
        if (!cancelled) {
          setRegistrySettled(true)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    getRoles()
      .then((nextRoles) => {
        if (cancelled) {
          return
        }
        setRolesData(nextRoles)
      })
      .catch((error) => {
        toast.error(copilotBackendErrorMessage(error, 'Copilot roles unavailable'))
      })
      .finally(() => {
        if (!cancelled) {
          setRolesSettled(true)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (roleOptions.length === 0) {
      return
    }
    if (roleOptions.some((option) => option.role === selectedRole)) {
      return
    }
    setSelectedRole(roleOptions[0].role)
  }, [roleOptions, selectedRole])

  // F3: the selected display role IS the single role/route truth for the
  // composer — same derivation Settings renders, never registry.roles.
  const selectedOption = roleOptions.find((option) => option.role === selectedRole) ?? roleOptions[0] ?? null
  const selectedRoleKey = selectedOption?.role ?? ''
  const defaultRouteId = selectedOption?.fallbackChain[0]?.route_id ?? ''
  // Attach 与 Close 覆盖同一个集合：有运行时就既能看它、也能关它。残留（`lingering`）
  // 也在里面——ah 有意留着的那块死窗格正是使用者想看的最后一屏（PM 裁决 2026-08-04）。
  const closableCodeAssistants = closableCodeAssistantIds(codeAssistantStatus)
  const codeAssistantCloseLabel = codeAssistantCloseButtonLabel(codeAssistantStatus)
  const codeAssistantAttachLabels = codeAssistantAttachMenuLabels(codeAssistantStatus)
  const isClaudeOpenDisabled = codeAssistantStatus.claude.status === 'inactive' && isAssistantReadOnly(codeAssistantStatus.claude)
  const isCodexOpenDisabled = codeAssistantStatus.codex.status === 'inactive' && isAssistantReadOnly(codeAssistantStatus.codex)
  const allReadOnlyInactive = isClaudeOpenDisabled && isCodexOpenDisabled
  // 进行态优先级低于"真有东西在跑":claude 在跑而 codex 正在启动时,头部仍然给
  // Attach/Close(那是此刻唯一有用的动作),不被一个 spinner 顶掉。
  const codeAssistantPending = codeAssistantPendingLabel(codeAssistantStatus)
  const pickerRole = useMemo(
    () => (selectedOption ? { fallback_chain: selectedOption.fallbackChain } : null),
    [selectedOption],
  )

  useEffect(() => {
    setSelectedRouteId(defaultRouteId)
  }, [selectedRoleKey, defaultRouteId])

  function selectRoute(routeId: string) {
    if (routeId === selectedRouteId) {
      return
    }
    setSelectedRouteId(routeId)
    toast.info('Route switched. Future messages will use it.')
  }

  const refreshCodeAssistantStatus = useCallback(async () => {
    if (!codeAssistantWorkspace) {
      setCodeAssistantStatus(unobservedCodeAssistantStatus())
      return
    }
    await ensureCodeAssistantStatusEvents(codeAssistantWorkspace)
  }, [codeAssistantWorkspace])

  useEffect(() => {
    let cancelled = false
    if (!codeAssistantWorkspace) {
      setCodeAssistantStatus(unobservedCodeAssistantStatus())
      return () => {
        cancelled = true
      }
    }

    let unsubscribe: (() => void) | null = null
    setCodeAssistantStatus(unobservedCodeAssistantStatus())
    void subscribeCodeAssistantStatus(codeAssistantWorkspace, (nextStatus) => {
      if (!cancelled) {
        setCodeAssistantStatus(nextStatus)
      }
    })
      .then((dispose) => {
        if (cancelled) {
          dispose()
          return
        }
        unsubscribe = dispose
      })
      .catch(() => {
        if (!cancelled) {
          setCodeAssistantStatus(unobservedCodeAssistantStatus())
        }
      })
    return () => {
      cancelled = true
      unsubscribe?.()
    }
  }, [codeAssistantWorkspace])

  // Starting a CLI is a user intent, so it happens here in the click handler —
  // never inside the terminal's render effect, which React runs twice in
  // development and would turn into a second `ah start` (§10 D2).
  async function startCliSession(assistant: CodeAssistantId, mode: 'open' | 'attach') {
    if (!codeAssistantWorkspace) return
    cliSession?.detach()
    const session = await startCliTerminalSession({
      workspaceRoot: codeAssistantWorkspace,
      assistant,
      mode,
      // The renderer reports its measured grid as soon as it mounts; this only
      // shapes the very first frame.
      grid: { cols: 100, rows: 30 },
      onExit: () => {
        onCliSessionChange?.(null)
        void refreshCodeAssistantStatus()
      },
    })
    onCliSessionChange?.(session)
    if (session) await refreshCodeAssistantStatus()
  }

  function handleOpenCodeAssistant(assistant: CodeAssistantId) {
    if (isAssistantReadOnly(codeAssistantStatus[assistant])) {
      return
    }
    void startCliSession(assistant, 'open')
  }

  function handleAttachCodeAssistant(assistant: CodeAssistantId) {
    void startCliSession(assistant, 'attach')
  }

  async function handleCloseCodeAssistants() {
    if (closableCodeAssistants.length === 0) {
      return
    }
    setClosingCodeAssistant(true)
    // Drop the local terminal client first, so the ah cleanup below is not
    // racing a live tmux attach.
    cliSession?.detach()
    onCliSessionChange?.(null)
    try {
      const readOnlyAssistants = closableCodeAssistants.filter((id) => isAssistantReadOnly(codeAssistantStatus[id]))
      const writeAssistants = closableCodeAssistants.filter((id) => !isAssistantReadOnly(codeAssistantStatus[id]))

      if (writeAssistants.length > 0) {
        await Promise.all(
          writeAssistants.map((assistant) => closeCodeAssistant(codeAssistantWorkspace, assistant))
        )
      }

      if (readOnlyAssistants.length > 0 && copilot.activeSessionId) {
        if (typeof copilot.closeSession === 'function') {
          await copilot.closeSession(copilot.activeSessionId)
        }
      }

      await refreshCodeAssistantStatus()
    } finally {
      setClosingCodeAssistant(false)
    }
  }

  async function sendDraft() {
    if (!draft.trim() || copilot.connectionStatus !== 'open') {
      return
    }
    const activeJudgeContext = nextDraftJudgeContext(draft, draftJudgeContext, { skillId, view, judgeRefs })
    let roleKey = selectedOption?.role ?? null
    if (selectedOption && rolesData) {
      const resolution = resolveCopilotSendRole(rolesData, selectedOption, registry?.model_groups ?? [])
      roleKey = resolution.roleKey
      if (resolution.nextRoles) {
        // First use of a floated built-in materializes it (atom-56 ①) through
        // the same PUT path Settings uses, then the send carries the yaml key.
        try {
          const saved = await putRoles(resolution.nextRoles)
          setRolesData(saved)
          setSelectedRole(resolution.roleKey)
        } catch (error) {
          toast.error(copilotBackendErrorMessage(error, 'Copilot role could not be saved'))
          return
        }
      }
    }
    if (copilot.sendMessage(
      draft,
      selectedRouteId || defaultRouteId || null,
      roleKey,
      activeJudgeContext,
    )) {
      setDraft('')
      setDraftJudgeContext(null)
    }
  }

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void sendDraft()
  }

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (!isComposerSendKey(event)) {
      return
    }
    event.preventDefault()
    void sendDraft()
  }

  return (
    <aside className="studio-copilot-panel studio-canvas-panel z-copilot flex h-full min-h-0 flex-col border-l text-foreground">
      <header className="studio-canvas-panel-header border-b px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            {/* R5-E identity: MoirAI — named after the Moirai, the three Greek
                Fates who spin, measure and cut the thread of every life; this
                copilot weaves a skill's loose phases into one runnable DAG. The
                mark is the constellation Cassiopeia, which reads at once as an
                M, a star constellation, and a node-edge graph. Design source:
                docs/studio/mvp1/03_regions/copilot/mvp1-alignment.md (F1 · R5-E).
                The mark itself is the collapse control (PM「收的按钮去掉，点 logo
                收」) — no separate close button in the header. Colour is the one-
                shade-lighter accent-strong (PM「logo 的颜色浅一号」). */}
            {onCollapse ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    aria-label="收起 MoirAI"
                    onClick={onCollapse}
                    className="flex shrink-0 items-center justify-center rounded-sm outline-none transition-opacity hover:opacity-70 focus-visible:ring-2 focus-visible:ring-[color:var(--studio-canvas-accent)]"
                  >
                    <MoiraiMark className="size-[18px] text-[color:var(--studio-canvas-accent-strong)]" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom">收起</TooltipContent>
              </Tooltip>
            ) : (
              <MoiraiMark className="size-[18px] shrink-0 text-[color:var(--studio-canvas-accent-strong)]" title="MoirAI" />
            )}
            {/* shrink-0: the short name must never be squeezed out by the
                reconnect chip (the chip truncates instead). */}
            <h2 className="shrink-0 text-sm font-semibold">
              Moir<span className="text-[color:var(--studio-canvas-accent-strong)]">AI</span>
            </h2>
            {copilot.connectionStatus !== 'open' ? (
              <span className="inline-flex shrink-0 items-center rounded border border-destructive/40 bg-destructive/10 px-1.5 py-0.5 text-[0.625rem] text-muted-foreground">
                {copilot.connectionStatus}
                {copilot.reconnectInMs ? ` · retry ${Math.round(copilot.reconnectInMs / 1000)}s` : ''}
              </span>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {codeAssistantCloseLabel ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={closingCodeAssistant || !codeAssistantWorkspace}
                    aria-label="Manage code assistant"
                    className="studio-canvas-input-surface shrink-0"
                  >
                    <MonitorCheck data-icon="inline-start" />
                    CLI running
                    <ChevronDown className="size-3" aria-hidden="true" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-44">
                  {closableCodeAssistants.map((assistant, index) => (
                    <DropdownMenuItem
                      key={`attach-${assistant}`}
                      disabled={closingCodeAssistant || !codeAssistantWorkspace}
                      onSelect={() => {
                        handleAttachCodeAssistant(assistant)
                      }}
                    >
                      <SquareTerminal data-icon="inline-start" />
                      {codeAssistantAttachLabels[index] ?? `Attach ${codeAssistantLabel(assistant)}`}
                    </DropdownMenuItem>
                  ))}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    disabled={closingCodeAssistant || !codeAssistantWorkspace}
                    onSelect={() => {
                      void handleCloseCodeAssistants()
                    }}
                  >
                    <Square data-icon="inline-start" className="fill-current" />
                    {codeAssistantCloseLabel}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : codeAssistantPending ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled
                aria-label="Code assistant pending"
                aria-busy="true"
                className="studio-canvas-input-surface shrink-0"
              >
                <Loader2 className="size-3.5 animate-spin" data-icon="inline-start" />
                {codeAssistantPending}
              </Button>
            ) : (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!codeAssistantWorkspace || allReadOnlyInactive}
                    aria-label="Open code assistant"
                    className="studio-canvas-input-surface shrink-0"
                    title={allReadOnlyInactive ? 'Workspace-owned config is read-only' : undefined}
                  >
                    <SquareTerminal data-icon="inline-start" />
                    Open in CLI {allReadOnlyInactive && '(read-only)'}
                    <ChevronDown className="size-3" aria-hidden="true" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-36">
                  <DropdownMenuItem
                    disabled={!codeAssistantWorkspace || isClaudeOpenDisabled}
                    onSelect={() => {
                      handleOpenCodeAssistant('claude')
                    }}
                    title={codeAssistantStatus.claude.readOnly ? 'Workspace-owned config is read-only' : undefined}
                  >
                    Claude code {isClaudeOpenDisabled && '(read-only)'}
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    disabled={!codeAssistantWorkspace || isCodexOpenDisabled}
                    onSelect={() => {
                      handleOpenCodeAssistant('codex')
                    }}
                    title={codeAssistantStatus.codex.readOnly ? 'Workspace-owned config is read-only' : undefined}
                  >
                    Codex {isCodexOpenDisabled && '(read-only)'}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </div>
      </header>

      {cliSession ? (
        /* §10 D1: the CLI session's terminal takes over this region — chat and
           terminal are mutually exclusive, and the header control above stays
           the only way to attach or close a CLI (§10 D4). */
        <div data-studio-cli-terminal-region="true" className="flex min-h-0 flex-1 flex-col">
          <Suspense fallback={<div className="min-h-0 flex-1" />}>
            <CliTerminalView key={cliSession.id} session={cliSession} />
          </Suspense>
        </div>
      ) : (
      <>
      <SessionTabs
        sessions={copilot.sessions}
        activeSessionId={copilot.activeSessionId}
        onSwitch={copilot.switchSession}
        onNew={copilot.newSession}
        onRestore={copilot.restoreSession}
        onClose={copilot.closeSession}
      />

      {inEvalView && judgeRefs ? (
        <div className="shrink-0 border-b px-3 py-2 [border-color:var(--studio-canvas-border-soft)]">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!skillId}
            onClick={() => {
              void askCopilotJudge()
            }}
            className="studio-canvas-input-surface w-full justify-start"
          >
            Ask Copilot Judge
          </Button>
        </div>
      ) : null}

      {/* PM 2026-07-03: the answer must follow to the bottom in real time while it
          streams. `autoScroll` (defaultScrollPosition="end") sticks the viewport
          to the bottom as the assistant content grows. We deliberately do NOT mark
          the user message as a scrollAnchor: an anchor re-pins the viewport to that
          message (top of the turn), which leaves the streaming answer below the fold
          and DISABLES the stick-to-bottom follow — the exact "不会实时滚动到最底下"
          bug. No anchor → pure stick-to-bottom during streaming. */}
      <MessageScrollerProvider autoScroll>
        <MessageScroller className="min-h-0 flex-1">
          <MessageScrollerViewport className="p-4">
            <MessageScrollerContent className="gap-3">
        {copilot.messages.length > 0 ? (
          <>
            {copilot.messages.map((message) => (
              <MessageScrollerItem key={message.id} messageId={message.id}>
                <ChatMessageItem
                  message={message}
                  skillId={skillId}
                  workspaceRoot={workspaceRoot}
                  onFileChanged={onFileChanged}
                />
              </MessageScrollerItem>
            ))}
            {copilot.messages[copilot.messages.length - 1]?.role === 'user' ? (
              // Pre-event gap: the assistant message only exists once the first
              // ws event lands; until then the wait must still be visible.
              <MessageScrollerItem messageId="__thinking__">
                <ThinkingRow />
              </MessageScrollerItem>
            ) : null}
          </>
        ) : (
          <div className="studio-canvas-input-surface rounded-md border border-dashed p-3 text-sm text-muted-foreground">
            <div className="copilot-prose text-sm text-muted-foreground">
              <ReactMarkdown>
                {skillId
                  ? inEvalView
                    ? '**Copilot Judge**\n\nAsk me to review the current artifact and golden diff. I use the Eval context endpoint, not a separate judge backend.'
                    : 'Ask about this skill, workflow, or current screen. General questions are allowed.'
                  : '**Create a skill with Copilot**\n\nUse Templates as a scaffold, or describe the Skill you want me to help create.'}
              </ReactMarkdown>
            </div>
            {!skillId ? (
              <div className="mt-3 space-y-2">
                <button
                  type="button"
                  onClick={() => setDraft('Help me create a new Skill. Ask clarifying questions, then propose a minimal skill.md.')}
                  className="studio-canvas-input-surface w-full rounded-md border px-2 py-1.5 text-start text-xs font-medium text-foreground hover:bg-muted"
                >
                  Describe my Skill
                </button>
                <div className="text-xs">
                  {templatesLoading ? 'Loading templates...' : 'Templates'}
                  <div className="mt-1 flex flex-wrap gap-1">
                    {templates.slice(0, 3).map((template) => (
                      <button
                        key={template.id}
                        type="button"
                        onClick={() => setDraft(`Use the "${template.name}" template as a scaffold and help me create a Skill.`)}
                        className="studio-canvas-input-surface rounded-md border px-2 py-1 text-xs text-foreground hover:bg-muted"
                      >
                        {template.name}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        )}
        {copilot.lastError ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            {copilot.lastError}
          </div>
        ) : null}
            </MessageScrollerContent>
          </MessageScrollerViewport>
          <MessageScrollerButton />
        </MessageScroller>
      </MessageScrollerProvider>

      {skillId && completedRunId && completedRunId !== dismissedRunId ? (
        <div className="px-4 pt-1 shrink-0">
          <AnalysisBar
            skillId={skillId}
            runId={completedRunId}
            workspaceRoot={workspaceRoot}
            onJudgePrepared={handleJudgePrepared}
            onDismiss={() => setDismissedRunId(completedRunId)}
          />
        </div>
      ) : null}

      <form onSubmit={submit} className="shrink-0 space-y-1.5 px-4 pb-4 pt-2">
        <div className="studio-copilot-input studio-canvas-input-surface flex flex-col gap-1 rounded-md border px-2.5 py-2 transition-colors focus-within:[border-color:var(--studio-canvas-accent-muted)]">
          <textarea
            value={draft}
            onChange={(event) => {
              const nextDraft = event.target.value
              setDraft(nextDraft)
              setDraftJudgeContext((current) => nextDraftJudgeContext(nextDraft, current, { skillId, view, judgeRefs }))
            }}
            onKeyDown={handleComposerKeyDown}
            rows={3}
            className="min-h-[60px] max-h-[160px] w-full resize-none overflow-y-auto bg-transparent text-sm leading-relaxed outline-none field-sizing-content placeholder:text-muted-foreground"
            placeholder="Use '@' to mention nodes..."
          />
          {/* F6: inside the bordered box only the send action lives (stop joins it
              with F7-③ interrupt); every settings control sits BELOW the box. */}
          <div className="flex items-center justify-end">
            {copilot.isStreaming ? (
              /* R7-I: while a turn streams, the send action becomes a stop button
                 (SDK-native interrupt). The turn's own done event flips it back. */
              <button
                type="button"
                onClick={() => {
                  void copilot.interrupt()
                }}
                aria-label="Stop generating"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-secondary text-secondary-foreground transition-colors hover:bg-secondary/80"
              >
                <Square className="size-3 fill-current" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!draft.trim() || copilot.connectionStatus !== 'open'}
                aria-label="Send message"
                className={`inline-flex h-7 w-7 items-center justify-center rounded-md transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${
                  draft.trim() && copilot.connectionStatus === 'open'
                    ? 'bg-[color:var(--studio-canvas-accent)] text-primary-foreground hover:bg-primary/80'
                    : 'bg-secondary text-secondary-foreground'
                }`}
              >
                <ArrowUp className={`size-3.5 ${!draft.trim() ? 'text-muted-foreground' : ''}`} />
              </button>
            )}
          </div>
        </div>
        {/* F7 context actions (attach / @mention) join the left side of this row
            once they are functional — no dead placeholders. */}
        <div className="flex items-center justify-end gap-0.5">
          {/* R7-C (PM 2026-07-02): the role anchor is ALWAYS present. While config
              loads it shows the fixed default (opus4.8) + a spinner (the loading
              state lives inside RolePicker), not a skeleton block that swaps the
              whole picker out. The route picker still waits for a settled registry —
              routes are derived from it, so there is nothing to show until then. */}
          {registrySettled && rolesSettled && (
            <ModelPicker
              role={pickerRole}
              registry={registry}
              selectedRouteId={selectedRouteId || defaultRouteId}
              onSelect={selectRoute}
            />
          )}
          <RolePicker
            options={roleOptions}
            selectedRole={selectedRoleKey}
            onSelect={setSelectedRole}
            loading={!(registrySettled && rolesSettled)}
          />
        </div>
      </form>
      </>
      )}
    </aside>
  )
}

export function buildCopilotJudgeDraft(refs: CopilotJudgeResponse): string {
  const contextJson = JSON.stringify(
    {
      compare_result_ref: refs.compare_result_ref,
      judge_context_ref: refs.judge_context_ref,
      baseline_ref: refs.baseline_ref,
      diff_summary: refs.diff_summary,
    },
    null,
    2,
  )
  return [
    'Judge the current Eval diff. Explain the likely cause, risk, and whether this should become a new golden baseline.',
    '',
    'Use this structured Copilot Judge context:',
    contextJson,
  ].join('\n')
}
