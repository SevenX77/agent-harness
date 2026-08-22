// @vitest-environment jsdom

import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CopilotMessage } from '../../types/copilot'
import {
  buildCopilotJudgeDraft,
  buildGoldenDesignDraft,
  codeAssistantAttachEntries,
  codeAssistantCloseAction,
  codeAssistantPendingPhase,
  copilotBackendErrorMessage,
  CopilotPanel,
  nextDraftJudgeContext,
} from './copilot-panel'
import { isComposerSendKey } from './composer/composer-keys'
import { BACKEND_UNAVAILABLE_MESSAGE } from '@/utils/errors'
import { toast } from 'sonner'

const mocks = vi.hoisted(() => ({
  useCopilot: vi.fn(),
  useTemplates: vi.fn(),
  getRegistry: vi.fn(),
  getRoles: vi.fn(),
  prepareCopilotJudgeContext: vi.fn(),
  openClaudeCode: vi.fn(),
  openCodexCli: vi.fn(),
  lastOpenedCodeAssistant: vi.fn(),
  attachCodeAssistant: vi.fn(),
  ensureCodeAssistantStatusEvents: vi.fn(),
  subscribeCodeAssistantStatus: vi.fn(),
  closeCodeAssistant: vi.fn(),
  buttonProps: [] as Array<Record<string, unknown>>,
  menuItemProps: [] as Array<Record<string, unknown>>,
}))

vi.mock('../../api/client', () => ({
  prepareCopilotJudgeContext: mocks.prepareCopilotJudgeContext,
}))

vi.mock('../../api/llm', () => ({
  getRegistry: mocks.getRegistry,
  getRoles: mocks.getRoles,
  putRoles: vi.fn(),
}))

// Only the hook is faked — the pure rules it exports (what makes a turn worth
// sending) stay real, so the panel is tested against the same rule the socket
// layer applies rather than against a stub that agrees with it by default.
vi.mock('../../hooks/useCopilot', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../hooks/useCopilot')>()),
  useCopilot: mocks.useCopilot,
}))

vi.mock('../../hooks/useStudioEventStream', () => ({
  useStudioEventStream: vi.fn(),
}))

vi.mock('../../hooks/useTemplates', () => ({
  useTemplates: mocks.useTemplates,
}))

vi.mock('../../lib/tauri', () => ({
  openClaudeCode: mocks.openClaudeCode,
  openCodexCli: mocks.openCodexCli,
  lastOpenedCodeAssistant: mocks.lastOpenedCodeAssistant,
  attachCodeAssistant: mocks.attachCodeAssistant,
  ensureCodeAssistantStatusEvents: mocks.ensureCodeAssistantStatusEvents,
  subscribeCodeAssistantStatus: mocks.subscribeCodeAssistantStatus,
  closeCodeAssistant: mocks.closeCodeAssistant,
  // 挂载初值 = 尚未观测(决议 2026-08-03 D-C3);用真实实现,面板的 hands-off 断言才有意义。
  unobservedCodeAssistantStatus: () => ({
    claude: { status: 'unknown', readOnly: false },
    codex: { status: 'unknown', readOnly: false },
  }),
}))

vi.mock('./analysis-bar', () => ({
  AnalysisBar: () => null,
}))

vi.mock('./model-picker', () => ({
  ModelPicker: () => null,
}))

vi.mock('./role-picker', () => ({
  RolePicker: () => null,
  copilotRoleOptions: () => [],
}))

vi.mock('./session-tabs', () => ({
  SessionTabs: () => null,
}))

vi.mock('../ui/button', () => ({
  Button: (props: Record<string, unknown>) => {
    mocks.buttonProps.push(props)
    return React.createElement('button', props, props.children as React.ReactNode)
  },
}))

vi.mock('../ui/dropdown-menu', () => ({
  DropdownMenu: (props: Record<string, unknown>) =>
    React.createElement('div', { 'data-slot': 'dropdown-menu' }, props.children as React.ReactNode),
  DropdownMenuTrigger: (props: Record<string, unknown>) =>
    React.createElement(React.Fragment, null, props.children as React.ReactNode),
  DropdownMenuContent: (props: Record<string, unknown>) =>
    React.createElement('div', { 'data-slot': 'dropdown-menu-content' }, props.children as React.ReactNode),
  DropdownMenuItem: (props: Record<string, unknown>) => {
    mocks.menuItemProps.push(props)
    return React.createElement('button', props, props.children as React.ReactNode)
  },
  DropdownMenuSeparator: () => React.createElement('hr'),
}))

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    info: vi.fn(),
  },
}))

describe('isComposerSendKey', () => {
  it('sends on plain Enter only', () => {
    expect(isComposerSendKey({ key: 'Enter', shiftKey: false, isComposing: false })).toBe(true)
  })

  it('keeps Shift+Enter as a line break', () => {
    expect(isComposerSendKey({ key: 'Enter', shiftKey: true, isComposing: false })).toBe(false)
  })

  it('never sends while an IME composition is active', () => {
    expect(isComposerSendKey({ key: 'Enter', shiftKey: false, isComposing: true })).toBe(false)
  })

  it('ignores other keys', () => {
    expect(isComposerSendKey({ key: 'a', shiftKey: false, isComposing: false })).toBe(false)
  })
})


/** The composer, stubbed down to the two callbacks the panel talks to.
 *
 * What the real editor does with a pick is covered next door
 * (`composer/MentionComposer.test.tsx`); what is only visible HERE is whether
 * the panel carries the picked objects into the message it sends.
 */
const composerSeam = vi.hoisted(() => ({
  onChange: null as ((value: { text: string; mentions: unknown[] }) => void) | null,
  onSend: null as (() => void) | null,
  onImagesPasted: null as ((files: File[]) => void) | null,
}))

vi.mock('./composer/MentionComposer', () => ({
  MentionComposer: (props: {
    onChange: (value: { text: string; mentions: unknown[] }) => void
    onSend: () => void
    onImagesPasted?: (files: File[]) => void
  }) => {
    composerSeam.onChange = props.onChange
    composerSeam.onSend = props.onSend
    composerSeam.onImagesPasted = props.onImagesPasted ?? null
    return null
  },
}))

describe('buildCopilotJudgeDraft', () => {
  beforeEach(() => {
    mocks.getRegistry.mockResolvedValue({ roles: {} })
    mocks.getRoles.mockResolvedValue({})
    mocks.prepareCopilotJudgeContext.mockReset()
    mocks.openClaudeCode.mockReset()
    mocks.openClaudeCode.mockResolvedValue(true)
    mocks.openCodexCli.mockReset()
    mocks.openCodexCli.mockResolvedValue(true)
    mocks.lastOpenedCodeAssistant.mockReset()
    mocks.lastOpenedCodeAssistant.mockResolvedValue('claude')
    mocks.attachCodeAssistant.mockReset()
    mocks.attachCodeAssistant.mockResolvedValue(true)
    mocks.ensureCodeAssistantStatusEvents.mockReset()
    mocks.ensureCodeAssistantStatusEvents.mockResolvedValue(undefined)
    mocks.subscribeCodeAssistantStatus.mockReset()
    mocks.subscribeCodeAssistantStatus.mockResolvedValue(vi.fn())
    mocks.closeCodeAssistant.mockReset()
    mocks.closeCodeAssistant.mockResolvedValue(true)
    mocks.buttonProps.length = 0
    mocks.menuItemProps.length = 0
    mocks.useTemplates.mockReturnValue({ templates: [], templatesLoading: false })
    mocks.useCopilot.mockReturnValue(copilotState())
  })

  it('includes baseline and diff summary in the structured judge draft', () => {
    const draft = buildCopilotJudgeDraft({
      compare_result_ref: 'skill-1/golden/golden-1/compare/run-1/compare_result.json',
      judge_context_ref: 'skill-1/runs/run-1/copilot_judge/golden-1/judge_context.json',
      baseline_ref: 'skill-1/golden/golden-1/baseline.json',
      diff_summary: {
        baseline_id: 'golden-1',
        run_results_ref: 'skill-1/runs/run-1/result.json',
        total_score: 80,
        node_group_count: 1,
        failed_node_count: 1,
      },
    })

    expect(draft).toContain('"baseline_ref": "skill-1/golden/golden-1/baseline.json"')
    expect(draft).toContain('"diff_summary"')
    expect(draft).toContain('"failed_node_count": 1')
  })

  it('keeps Ask Copilot Judge available when eval messages already exist', () => {
    mocks.useCopilot.mockReturnValue(copilotState({
      messages: [
        {
          id: 'assistant-1',
          role: 'assistant',
          content: 'Existing judge conversation',
          events: [],
          status: 'success',
          createdAt: 1,
        },
      ],
    }))

    const html = renderToStaticMarkup(
      React.createElement(CopilotPanel, {
        skillId: 'text-segmentation',
        copilot: mocks.useCopilot(),
        view: 'eval',
        judgeRefs: {
          runResultsRef: 'text-segmentation/runs/run-1/result.json',
          baselineRef: 'text-segmentation/golden/golden-1/baseline.json',
        },
      }),
    )

    expect(html).toContain('Existing judge conversation')
    expect(html).toContain('Ask Copilot Judge')
  })

  it('uses the shared canvas overlay surface so Copilot matches Studio panels', () => {
    const html = renderToStaticMarkup(
      React.createElement(CopilotPanel, {
        skillId: 'text-segmentation',
        copilot: mocks.useCopilot(),
      }),
    )

    expect(html).toContain('studio-copilot-panel')
    expect(html).toContain('studio-canvas-panel')
    expect(html).toContain('studio-copilot-input')
  })

  it('does not load templates when the current skill chat does not show template UI', () => {
    renderToStaticMarkup(
      React.createElement(CopilotPanel, {
        skillId: 'text-segmentation',
        copilot: mocks.useCopilot(),
      }),
    )

    expect(mocks.useTemplates).toHaveBeenCalledWith({ enabled: false })
  })

  it('loads templates only for the create-skill empty state where templates are visible', () => {
    renderToStaticMarkup(
      React.createElement(CopilotPanel, {
        skillId: null,
        copilot: mocks.useCopilot(),
      }),
    )

    expect(mocks.useTemplates).toHaveBeenCalledWith({ enabled: true })
  })

  it('starts the CLI session from the menu click, not from a render effect', async () => {
    // §10 D2: starting a CLI is a user intent. React mounts effects twice in
    // development, and `ah start` rejects the second call as "still starting",
    // so the launch must hang off the click handler and nothing else.
    // 挂载初值是"尚未观测",此时头部是进行态控件、根本没有 Open 菜单,所以这条必须先
    // 喂一帧真实快照把面板带到可 Open 的状态,再验"启动只由点击触发"。
    const previousReactActEnvironment = (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean })
      .IS_REACT_ACT_ENVIRONMENT
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    let emitStatus: ((status: unknown) => void) | null = null
    mocks.subscribeCodeAssistantStatus.mockImplementation(async (_workspaceRoot, onStatus) => {
      emitStatus = onStatus
      return vi.fn()
    })
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root: Root = createRoot(container)
    await act(async () => {
      root.render(React.createElement(CopilotPanel, {
        skillId: 'text-segmentation',
        copilot: mocks.useCopilot(),
        workspaceRoot: '/tmp/text-segmentation',
      }))
    })
    await act(async () => {
      emitStatus?.({
        claude: { status: 'inactive', readOnly: false },
        codex: { status: 'inactive', readOnly: false },
      })
    })

    const openButton = mocks.buttonProps.find((props) => props['aria-label'] === 'Open code assistant')
    expect(openButton).toBeTruthy()
    expect(container.textContent).toContain('Open in CLI')

    // Rendering the panel alone must not have launched anything.
    expect(mocks.openClaudeCode).not.toHaveBeenCalled()

    const menuText = (props: Record<string, unknown>) =>
      renderToStaticMarkup(React.createElement(React.Fragment, null, props.children as React.ReactNode))
    const claudeItem = mocks.menuItemProps.find((props) => menuText(props).includes('Claude code'))
    expect(claudeItem).toBeTruthy()

    ;(claudeItem?.onSelect as (() => void) | undefined)?.()

    await vi.waitFor(() => {
      expect(mocks.openClaudeCode).toHaveBeenCalledTimes(1)
    })
    const [workspaceRoot, grid] = mocks.openClaudeCode.mock.calls[0] as [string, { cols: number; rows: number }]
    expect(workspaceRoot).toBe('/tmp/text-segmentation')
    expect(grid.cols).toBeGreaterThan(0)
    expect(grid.rows).toBeGreaterThan(0)

    act(() => {
      root.unmount()
    })
    document.body.removeChild(container)
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
      previousReactActEnvironment
  })

  it('offers Resume Claude code and launches it with the resume semantic', async () => {
    // 决议 2026-08-05 D-F2/F-5 + 2026-08-06 D-G2 —— Open 下拉里的 Resume 项指向
    // 「上次打开的 CLI」(此处 mock 为 claude),点击走与 Open 同一条启动流程,但以
    // resume 语义调用(openClaudeCode 收到 { resumeLastConversation: true });
    // 普通 Open 不带该语义。
    const previousReactActEnvironment = (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean })
      .IS_REACT_ACT_ENVIRONMENT
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    let emitStatus: ((status: unknown) => void) | null = null
    mocks.subscribeCodeAssistantStatus.mockImplementation(async (_workspaceRoot, onStatus) => {
      emitStatus = onStatus
      return vi.fn()
    })
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root: Root = createRoot(container)

    try {
      await act(async () => {
        root.render(React.createElement(CopilotPanel, {
          skillId: 'text-segmentation',
          copilot: mocks.useCopilot(),
          workspaceRoot: '/tmp/text-segmentation',
        }))
      })
      await act(async () => {
        emitStatus?.({
          claude: { status: 'inactive', readOnly: false },
          codex: { status: 'inactive', readOnly: false },
        })
      })

      const menuText = (props: Record<string, unknown>) =>
        renderToStaticMarkup(React.createElement(React.Fragment, null, props.children as React.ReactNode))
      const resumeItem = mocks.menuItemProps.find((props) => menuText(props).includes('Resume Claude code'))
      expect(resumeItem).toBeTruthy()

      ;(resumeItem?.onSelect as (() => void) | undefined)?.()
      await vi.waitFor(() => {
        expect(mocks.openClaudeCode).toHaveBeenCalledTimes(1)
      })
      const resumeCall = mocks.openClaudeCode.mock.calls[0] as unknown[]
      expect(resumeCall[0]).toBe('/tmp/text-segmentation')
      expect(resumeCall[3]).toEqual({ resumeLastConversation: true })

      // 对照:普通 Open 不带 resume 语义。
      const claudeItem = mocks.menuItemProps.find((props) => {
        const text = menuText(props)
        return text.includes('Claude code') && !text.includes('Resume')
      })
      ;(claudeItem?.onSelect as (() => void) | undefined)?.()
      await vi.waitFor(() => {
        expect(mocks.openClaudeCode).toHaveBeenCalledTimes(2)
      })
      const openCall = mocks.openClaudeCode.mock.calls[1] as unknown[]
      expect(openCall[3]).toEqual({ resumeLastConversation: false })
    } finally {
      act(() => {
        root.unmount()
      })
      document.body.removeChild(container)
      ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
        previousReactActEnvironment
    }
  })

  it('labels Resume after the last-opened CLI and resumes codex with the resume semantic', async () => {
    // 决议 2026-08-06 D-G2/D-G3 —— 上次用 codex 打开的工作区,Resume 项显示
    // "Resume Codex",点击以 resume 语义调用 openCodexCli。
    mocks.lastOpenedCodeAssistant.mockResolvedValue('codex')
    const previousReactActEnvironment = (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean })
      .IS_REACT_ACT_ENVIRONMENT
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    let emitStatus: ((status: unknown) => void) | null = null
    mocks.subscribeCodeAssistantStatus.mockImplementation(async (_workspaceRoot, onStatus) => {
      emitStatus = onStatus
      return vi.fn()
    })
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root: Root = createRoot(container)

    try {
      await act(async () => {
        root.render(React.createElement(CopilotPanel, {
          skillId: 'text-segmentation',
          copilot: mocks.useCopilot(),
          workspaceRoot: '/tmp/text-segmentation',
        }))
      })
      await act(async () => {
        emitStatus?.({
          claude: { status: 'inactive', readOnly: false },
          codex: { status: 'inactive', readOnly: false },
        })
      })

      const menuText = (props: Record<string, unknown>) =>
        renderToStaticMarkup(React.createElement(React.Fragment, null, props.children as React.ReactNode))
      expect(mocks.menuItemProps.find((props) => menuText(props).includes('Resume Claude code'))).toBeFalsy()
      const resumeItem = mocks.menuItemProps.find((props) => menuText(props).includes('Resume Codex'))
      expect(resumeItem).toBeTruthy()

      ;(resumeItem?.onSelect as (() => void) | undefined)?.()
      await vi.waitFor(() => {
        expect(mocks.openCodexCli).toHaveBeenCalledTimes(1)
      })
      const resumeCall = mocks.openCodexCli.mock.calls[0] as unknown[]
      expect(resumeCall[0]).toBe('/tmp/text-segmentation')
      expect(resumeCall[3]).toEqual({ resumeLastConversation: true })
    } finally {
      act(() => {
        root.unmount()
      })
      document.body.removeChild(container)
      ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
        previousReactActEnvironment
    }
  })

  it('hides the Resume item when the workspace has no launch record', async () => {
    // 决议 2026-08-06 D-G2 —— 没有「上次打开」记录就没有可恢复对象,不渲染 Resume 项
    // (读不到记录 = 安全降级为隐藏,不是置灰假按钮)。
    mocks.lastOpenedCodeAssistant.mockResolvedValue(null)
    const previousReactActEnvironment = (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean })
      .IS_REACT_ACT_ENVIRONMENT
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    let emitStatus: ((status: unknown) => void) | null = null
    mocks.subscribeCodeAssistantStatus.mockImplementation(async (_workspaceRoot, onStatus) => {
      emitStatus = onStatus
      return vi.fn()
    })
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root: Root = createRoot(container)

    try {
      await act(async () => {
        root.render(React.createElement(CopilotPanel, {
          skillId: 'text-segmentation',
          copilot: mocks.useCopilot(),
          workspaceRoot: '/tmp/text-segmentation',
        }))
      })
      await act(async () => {
        emitStatus?.({
          claude: { status: 'inactive', readOnly: false },
          codex: { status: 'inactive', readOnly: false },
        })
      })

      const menuText = (props: Record<string, unknown>) =>
        renderToStaticMarkup(React.createElement(React.Fragment, null, props.children as React.ReactNode))
      expect(mocks.menuItemProps.find((props) => menuText(props).includes('Resume'))).toBeFalsy()
    } finally {
      act(() => {
        root.unmount()
      })
      document.body.removeChild(container)
      ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
        previousReactActEnvironment
    }
  })

  it('renders the CLI terminal from the session the WORKSPACE owns, not its own state', () => {
    // Collapsing the panel unmounts it. If the panel owned the session, the
    // running CLI would be lost on every collapse (and its terminal client
    // leaked); the workspace owns it and hands it down, so re-expanding
    // re-renders the same live session.
    const session = {
      id: 'claude-abc-1',
      assistant: 'claude' as const,
      attach: () => () => {},
      write: () => {},
      resize: () => {},
      detach: () => {},
    }
    const html = renderToStaticMarkup(
      React.createElement(CopilotPanel, {
        skillId: 'text-segmentation',
        copilot: mocks.useCopilot(),
        workspaceRoot: '/tmp/text-segmentation',
        cliSession: session,
        onCliSessionChange: () => {},
      }),
    )

    expect(html).toContain('data-studio-cli-terminal-region="true"')
    expect(html).not.toContain('to mention nodes')
  })

  it('derives the close button state from live ahd status', () => {
    // Migrated from the old `{claude,codex}` bool shape to the task-8 per-assistant payload
    // (design.md:290-297); the normal (non-read-only) close-label semantic is unchanged.
    // readOnly:false = Studio-managed, so an active assistant's control stays 'Close …' —
    // the read-only Detach case is covered by test_readonly_active_close_is_detach.
    const active = { status: 'active', readOnly: false } as const
    const inactive = { status: 'inactive', readOnly: false } as const
    expect(codeAssistantCloseAction({ claude: inactive, codex: inactive })).toBeNull()
    expect(codeAssistantCloseAction({ claude: active, codex: inactive })).toEqual({ kind: 'closeOne', assistant: 'claude' })
    expect(codeAssistantCloseAction({ claude: inactive, codex: active })).toEqual({ kind: 'closeOne', assistant: 'codex' })
    expect(codeAssistantCloseAction({ claude: active, codex: active })).toEqual({ kind: 'closeAll' })
  })

  it('offers BOTH Attach and Close for a lingering runtime, and says the session exited', () => {
    // PM 裁决 2026-08-04(取代决议 2026-08-02 D-A3):有残留就当作还有运行时——既能 attach
    // 上去看那块 `remain-on-exit` 留下的死窗格(ah 就是为了事后取证才留着它,那一屏正是
    // 使用者想看的:CLI 怎么退的、最后报了什么),也能 Close 把它清干净;清干净之前
    // `Open in CLI` 不出现。
    //
    // 但残留的入口必须标出"已退出",否则点下去看到一块冻住的窗格会被读成卡死。
    const lingering = { status: 'lingering', readOnly: false } as const
    const inactive = { status: 'inactive', readOnly: false } as const
    const active = { status: 'active', readOnly: false } as const

    expect(codeAssistantCloseAction({ claude: lingering, codex: inactive })).toEqual({ kind: 'closeOne', assistant: 'claude' })
    expect(codeAssistantCloseAction({ claude: inactive, codex: lingering })).toEqual({ kind: 'closeOne', assistant: 'codex' })
    expect(codeAssistantCloseAction({ claude: lingering, codex: active })).toEqual({ kind: 'closeAll' })

    expect(codeAssistantAttachEntries({ claude: lingering, codex: inactive })).toEqual([
      { assistant: 'claude', exited: true },
    ])
    // 对照组:活会话不带后缀 —— 证明后缀是按相位算出来的,不是常量。
    expect(codeAssistantAttachEntries({ claude: lingering, codex: active })).toEqual([
      { assistant: 'claude', exited: true },
      { assistant: 'codex', exited: false },
    ])
    expect(codeAssistantAttachEntries({ claude: inactive, codex: inactive })).toEqual([])
  })

  it('subscribes to ah runtime events so a delayed CLI start updates the button without polling', async () => {
    const setIntervalSpy = vi.spyOn(window, 'setInterval')
    const previousReactActEnvironment = (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean })
      .IS_REACT_ACT_ENVIRONMENT
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    // 决议 2026-08-03 D-C6:投影器不再接受 boolean 兼容形状,这里改用真实 payload。
    let emitStatus: ((status: unknown) => void) | null = null
    const unsubscribe = vi.fn()
    mocks.subscribeCodeAssistantStatus.mockImplementation(async (_workspaceRoot, onStatus) => {
      emitStatus = onStatus
      onStatus({
        claude: { status: 'inactive', readOnly: false },
        codex: { status: 'inactive', readOnly: false },
      })
      return unsubscribe
    })
    const container = document.createElement('div')
    document.body.appendChild(container)
    let root: Root | null = createRoot(container)

    try {
      await act(async () => {
        root?.render(React.createElement(CopilotPanel, {
          skillId: 'text-segmentation',
          copilot: mocks.useCopilot(),
          workspaceRoot: '/tmp/text-segmentation',
        }))
      })
      await vi.waitFor(() => {
        expect(container.textContent).toContain('Open in CLI')
      })

      await act(async () => {
        emitStatus?.({
          claude: { status: 'inactive', readOnly: false },
          codex: { status: 'active', readOnly: false },
        })
      })

      await vi.waitFor(() => {
        expect(mocks.subscribeCodeAssistantStatus).toHaveBeenCalledWith('/tmp/text-segmentation', expect.any(Function))
        expect(setIntervalSpy).not.toHaveBeenCalled()
        expect(container.textContent).toContain('CLI running')
      })
    } finally {
      act(() => {
        root?.unmount()
      })
      root = null
      document.body.removeChild(container)
      ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
        previousReactActEnvironment
      setIntervalSpy.mockRestore()
    }
  })

  it('derives attach menu entries from live ahd status', () => {
    // Migrated to the task-8 per-assistant payload shape; attach-label semantic unchanged.
    const active = { status: 'active', readOnly: false } as const
    const inactive = { status: 'inactive', readOnly: false } as const
    expect(codeAssistantAttachEntries({ claude: inactive, codex: inactive })).toEqual([])
    expect(codeAssistantAttachEntries({ claude: active, codex: inactive })).toEqual([
      { assistant: 'claude', exited: false },
    ])
    expect(codeAssistantAttachEntries({ claude: inactive, codex: active })).toEqual([
      { assistant: 'codex', exited: false },
    ])
    expect(codeAssistantAttachEntries({ claude: active, codex: active })).toEqual([
      { assistant: 'claude', exited: false },
      { assistant: 'codex', exited: false },
    ])
  })

  // ── studio-ah-state-contract-v1 task 9 (read-only Detach control semantics) RED tests ──
  //
  // Authored by g2 (泳道2 gatekeeper) test-first: g2-m1 turns these GREEN by wiring the
  // read-only control semantics of Req 6.4 / 5.14 and must NOT edit these tests. They ride
  // the reshaped per-assistant payload of task 8 (design.md:290-297):
  //   { claude: { status, reason?, readOnly }, codex: { status, reason?, readOnly } }
  // delivered here through the subscribeCodeAssistantStatus mock exactly as the live event
  // does. These assert the CONTRACT BOUNDARY the frontend controls: rendered controls the
  // user sees (Detach label / disabled Open + guidance) AND the lifecycle-command surface
  // (`closeCodeAssistant` invokes ah stop/ah kill; `openClaudeCode`/`openCodexCli` invoke
  // ah start). "no lifecycle command" is proven by those mocks never being called — not by
  // an internal flag. See tasks.md task 9 (111-118), design.md:296-301/310, Req 6.4/5.14.

  it('test_readonly_active_close_is_detach', async () => {
    // Req 6.4 / 5.14: a workspace-owned (readOnly) assistant that is active presents its Close
    // control as Detach — local tab close only, emitting NO ah stop / ah kill. RED today: the
    // panel has no Detach path — it labels the control "Close …" and Close calls
    // closeCodeAssistant (the ah stop/kill boundary).
    const previousReactActEnvironment = (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean })
      .IS_REACT_ACT_ENVIRONMENT
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    let emitStatus: ((status: unknown) => void) | null = null
    const unsubscribe = vi.fn()
    mocks.subscribeCodeAssistantStatus.mockImplementation(async (_workspaceRoot, onStatus) => {
      emitStatus = onStatus
      return unsubscribe
    })
    const container = document.createElement('div')
    document.body.appendChild(container)
    let root: Root | null = createRoot(container)

    try {
      await act(async () => {
        root?.render(React.createElement(CopilotPanel, {
          skillId: 'text-segmentation',
          copilot: mocks.useCopilot(),
          workspaceRoot: '/tmp/text-segmentation',
        }))
      })

      // A read-only assistant (workspace-owned config) that is ACTIVE.
      await act(async () => {
        emitStatus?.({
          claude: { status: 'active', readOnly: true },
          codex: { status: 'inactive', readOnly: true },
        })
      })

      // The active control resolves to Detach (not Close) for a read-only assistant.
      await vi.waitFor(() => {
        expect(container.textContent).toContain('Detach')
      })

      // Selecting Detach closes the local tab only — it must NOT emit ah stop / ah kill.
      const menuText = (props: Record<string, unknown>) =>
        renderToStaticMarkup(React.createElement(React.Fragment, null, props.children as React.ReactNode))
      const detachItem = mocks.menuItemProps.find((props) => menuText(props).includes('Detach'))
      expect(detachItem).toBeTruthy()
      await act(async () => {
        ;(detachItem?.onSelect as (() => void) | undefined)?.()
      })
      expect(mocks.closeCodeAssistant).not.toHaveBeenCalled()
    } finally {
      act(() => {
        root?.unmount()
      })
      root = null
      document.body.removeChild(container)
      ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
        previousReactActEnvironment
    }
  })

  it('test_readonly_inactive_open_disabled', async () => {
    // Req 6.4 / 5.14: a workspace-owned (readOnly) assistant that is inactive renders its Open
    // control disabled with guidance text, and issues NO lifecycle command (openClaudeCode /
    // openCodexCli both drive ah start). RED today: with both assistants inactive the panel
    // renders an ENABLED "Open in CLI" with clickable Claude/Codex items and no read-only
    // guidance. Guidance must live in the accessible DOM (button title / menu text), not a
    // portal-only tooltip, so it is observable here.
    const previousReactActEnvironment = (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean })
      .IS_REACT_ACT_ENVIRONMENT
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    let emitStatus: ((status: unknown) => void) | null = null
    const unsubscribe = vi.fn()
    mocks.subscribeCodeAssistantStatus.mockImplementation(async (_workspaceRoot, onStatus) => {
      emitStatus = onStatus
      return unsubscribe
    })
    const container = document.createElement('div')
    document.body.appendChild(container)
    let root: Root | null = createRoot(container)

    try {
      await act(async () => {
        root?.render(React.createElement(CopilotPanel, {
          skillId: 'text-segmentation',
          copilot: mocks.useCopilot(),
          workspaceRoot: '/tmp/text-segmentation',
        }))
      })

      // Both assistants read-only AND inactive (workspace-owned config, nothing running).
      await act(async () => {
        emitStatus?.({
          claude: { status: 'inactive', readOnly: true },
          codex: { status: 'inactive', readOnly: true },
        })
      })

      // The Open control is disabled, so no rejected lifecycle command can be triggered.
      await vi.waitFor(() => {
        const openButton = container.querySelector('button[aria-label="Open code assistant"]')
        expect(openButton).toBeTruthy()
        expect((openButton as HTMLButtonElement).disabled).toBe(true)
      })
      // …and it explains why (read-only workspace-owned config guidance, Req 6.4).
      expect(/read.?only/i.test(container.innerHTML)).toBe(true)
      expect(mocks.openClaudeCode).not.toHaveBeenCalled()
      expect(mocks.openCodexCli).not.toHaveBeenCalled()
    } finally {
      act(() => {
        root?.unmount()
      })
      root = null
      document.body.removeChild(container)
      ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
        previousReactActEnvironment
    }
  })

  // ── studio-ah-state-contract-v1 task 9 (starting/degraded button projection) RED tests ──
  //
  // Authored by g1 (泳道1 gatekeeper) test-first: g1-m1 turns these GREEN and must NOT edit
  // them. Today `isAssistantActive` (copilot-panel.tsx:286-291) collapses the 5-state contract
  // (tauri.ts:143-147) into a bare inactive-vs-not binary, so 'starting' and 'degraded' both
  // fall through the "active" branch and render the Attach/Close ("CLI running") control. These
  // pin the CONTRACT BOUNDARY the frontend controls — the rendered control the user actually
  // sees (trigger disabled state / presence) and whether an Attach/Close action is a clickable
  // (enabled) button — not any internal flag. They ride the task-8 per-assistant payload
  // ({ status, reason?, readOnly }) delivered through the subscribeCodeAssistantStatus mock:
  //   • starting → mid-transition, hands-off: the rendered control is disabled, NOT a clickable
  //                Attach/Close.
  //   • degraded → recoverable: a USABLE Open (cleanup-then-open) is exposed, NOT Attach/Close
  //                and NOT an all-dead set of buttons.

  it('test_starting_disables_buttons', async () => {
    // A CLI that is mid-start is hands-off: the panel shows a disabled control, never a
    // clickable Attach/Close. RED today — 'starting' !== 'inactive', so isAssistantActive
    // treats it as active and renders the ENABLED "CLI running" Attach/Close dropdown.
    const previousReactActEnvironment = (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean })
      .IS_REACT_ACT_ENVIRONMENT
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    let emitStatus: ((status: unknown) => void) | null = null
    const unsubscribe = vi.fn()
    mocks.subscribeCodeAssistantStatus.mockImplementation(async (_workspaceRoot, onStatus) => {
      emitStatus = onStatus
      return unsubscribe
    })
    const container = document.createElement('div')
    document.body.appendChild(container)
    let root: Root | null = createRoot(container)

    try {
      await act(async () => {
        root?.render(React.createElement(CopilotPanel, {
          skillId: 'text-segmentation',
          copilot: mocks.useCopilot(),
          workspaceRoot: '/tmp/text-segmentation',
        }))
      })

      // Claude CLI is starting (spawned, not yet ready); Codex idle.
      await act(async () => {
        emitStatus?.({
          claude: { status: 'starting', readOnly: false },
          codex: { status: 'inactive', readOnly: false },
        })
      })

      // The rendered assistant control is disabled while starting — hands-off.
      // 它现在呈现为带 spinner 的进行态("Starting…"),而不是一个外观与不可用无异的
      // 禁用 Open 触发器;hands-off 这条不变量本身没变。
      await vi.waitFor(() => {
        const control = container.querySelector(
          'button[aria-label="Code assistant pending"], button[aria-label="Manage code assistant"], button[aria-label="Open code assistant"]',
        )
        expect(control).toBeTruthy()
        expect((control as HTMLButtonElement).disabled).toBe(true)
        expect(control?.textContent).toContain('Starting…')
      })

      // …and no Attach/Close action is offered as a clickable (enabled) button.
      const enabledActionLabels = Array.from(container.querySelectorAll('button'))
        .filter((button) => !(button as HTMLButtonElement).disabled)
        .map((button) => button.textContent ?? '')
      expect(enabledActionLabels.some((text) => /Attach|Close/.test(text))).toBe(false)
    } finally {
      act(() => {
        root?.unmount()
      })
      root = null
      document.body.removeChild(container)
      ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
        previousReactActEnvironment
    }
  })

  // ── 决议 2026-08-03(status-stream ownership)—— 判据 C-8 / C-9 ──

  it('names the pending phase so a hands-off control never reads as broken', () => {
    // 进行态 ≠ 功能不可用。一个外观与"不可用"无异的禁用按钮会被读成"坏了",于是被反复
    // 点击;所以 hands-off 的两个相位各自有文案,渲染成带 spinner 的进行态。
    // `starting` 是更具体的事实(CLI 已经拉起),与 `unknown` 同时出现时它优先。
    const unknown = { status: 'unknown', readOnly: false } as const
    const starting = { status: 'starting', readOnly: false } as const
    const inactive = { status: 'inactive', readOnly: false } as const
    const active = { status: 'active', readOnly: false } as const

    expect(codeAssistantPendingPhase({ claude: unknown, codex: unknown })).toBe('checking')
    expect(codeAssistantPendingPhase({ claude: starting, codex: inactive })).toBe('starting')
    expect(codeAssistantPendingPhase({ claude: unknown, codex: starting })).toBe('starting')
    // 对照组:没有任何进行中的相位就没有进行态控件。
    expect(codeAssistantPendingPhase({ claude: inactive, codex: inactive })).toBeNull()
    expect(codeAssistantPendingPhase({ claude: active, codex: inactive })).toBeNull()
  })

  it('renders a spinning pending control instead of a look-alike disabled Open', async () => {
    // 挂载后一帧都还没到 ⇒ `unknown`:头部必须是"Checking…"+ spinner 的进行态,
    // 而不是一个看起来跟"不可用"一样的 `Open in CLI`。
    //
    // 回滚自检:把进行态分支删掉退回禁用的 Open 触发器,第一段断言立刻红;
    // 收到 active 帧后变成可管理控件那一段证明它不是恒定进行态。
    const previousReactActEnvironment = (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean })
      .IS_REACT_ACT_ENVIRONMENT
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    let emitStatus: ((status: unknown) => void) | null = null
    mocks.subscribeCodeAssistantStatus.mockImplementation(async (_workspaceRoot, onStatus) => {
      emitStatus = onStatus
      return vi.fn()
    })
    const container = document.createElement('div')
    document.body.appendChild(container)
    let root: Root | null = createRoot(container)

    try {
      await act(async () => {
        root?.render(React.createElement(CopilotPanel, {
          skillId: 'text-segmentation',
          copilot: mocks.useCopilot(),
          workspaceRoot: '/tmp/text-segmentation',
        }))
      })

      await vi.waitFor(() => {
        const pending = container.querySelector('button[aria-label="Code assistant pending"]')
        expect(pending).toBeTruthy()
        expect((pending as HTMLButtonElement).disabled).toBe(true)
        expect(pending?.getAttribute('aria-busy')).toBe('true')
        expect(pending?.textContent).toContain('Checking…')
        expect(pending?.querySelector('.animate-spin')).toBeTruthy()
      })
      expect(container.textContent).not.toContain('Open in CLI')

      // 观测到运行时在跑之后,进行态让位给真正有用的动作。
      await act(async () => {
        emitStatus?.({
          claude: { status: 'active', readOnly: false },
          codex: { status: 'inactive', readOnly: false },
        })
      })
      await vi.waitFor(() => {
        expect(container.querySelector('button[aria-label="Manage code assistant"]')).toBeTruthy()
        expect(container.querySelector('button[aria-label="Code assistant pending"]')).toBeNull()
      })
    } finally {
      act(() => {
        root?.unmount()
      })
      root = null
      document.body.removeChild(container)
      ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
        previousReactActEnvironment
    }
  })

  it('keeps the running control when one assistant is live and the other is mid-start', async () => {
    // 进行态不得顶掉"此刻唯一有用的动作":claude 在跑、codex 正在启动时,头部仍然是
    // Attach/Close。回滚自检:把进行态分支提到 close 分支之前,本例立刻红。
    const previousReactActEnvironment = (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean })
      .IS_REACT_ACT_ENVIRONMENT
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    let emitStatus: ((status: unknown) => void) | null = null
    mocks.subscribeCodeAssistantStatus.mockImplementation(async (_workspaceRoot, onStatus) => {
      emitStatus = onStatus
      return vi.fn()
    })
    const container = document.createElement('div')
    document.body.appendChild(container)
    let root: Root | null = createRoot(container)

    try {
      await act(async () => {
        root?.render(React.createElement(CopilotPanel, {
          skillId: 'text-segmentation',
          copilot: mocks.useCopilot(),
          workspaceRoot: '/tmp/text-segmentation',
        }))
      })
      await act(async () => {
        emitStatus?.({
          claude: { status: 'active', readOnly: false },
          codex: { status: 'starting', readOnly: false },
        })
      })

      await vi.waitFor(() => {
        const control = container.querySelector('button[aria-label="Manage code assistant"]')
        expect(control).toBeTruthy()
        expect((control as HTMLButtonElement).disabled).toBe(false)
      })
      expect(container.querySelector('button[aria-label="Code assistant pending"]')).toBeNull()
    } finally {
      act(() => {
        root?.unmount()
      })
      root = null
      document.body.removeChild(container)
      ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
        previousReactActEnvironment
    }
  })

  it('never routes an unobserved assistant into the closable set', async () => {
    // `unknown` 既不是"在跑"也不是"已回收":它不进 Attach 菜单,也不进 Close 那一类,
    // 否则面板会拿一个没有依据的状态去驱动生命周期动作。
    const unknown = { status: 'unknown', readOnly: false } as const
    const active = { status: 'active', readOnly: false } as const

    expect(codeAssistantCloseAction({ claude: unknown, codex: unknown })).toBeNull()
    expect(codeAssistantAttachEntries({ claude: unknown, codex: unknown })).toEqual([])
    // 对照组:另一侧真的在跑时,只有它进这两类。
    expect(codeAssistantCloseAction({ claude: unknown, codex: active })).toEqual({ kind: 'closeOne', assistant: 'codex' })
    expect(codeAssistantAttachEntries({ claude: unknown, codex: active })).toEqual([
      { assistant: 'codex', exited: false },
    ])
  })

  it('test_degraded_exposes_working_open', async () => {
    // A degraded CLI is recoverable: the panel exposes a USABLE Open (cleanup-then-open), not an
    // Attach/Close control and not an all-dead set of buttons. RED today — 'degraded' !==
    // 'inactive', so isAssistantActive treats it as active and renders the Attach/Close ("CLI
    // running") dropdown, so no "Open code assistant" button exists at all.
    const previousReactActEnvironment = (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean })
      .IS_REACT_ACT_ENVIRONMENT
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    let emitStatus: ((status: unknown) => void) | null = null
    const unsubscribe = vi.fn()
    mocks.subscribeCodeAssistantStatus.mockImplementation(async (_workspaceRoot, onStatus) => {
      emitStatus = onStatus
      return unsubscribe
    })
    const container = document.createElement('div')
    document.body.appendChild(container)
    let root: Root | null = createRoot(container)

    try {
      await act(async () => {
        root?.render(React.createElement(CopilotPanel, {
          skillId: 'text-segmentation',
          copilot: mocks.useCopilot(),
          workspaceRoot: '/tmp/text-segmentation',
        }))
      })

      // Claude CLI degraded (started but unhealthy); Codex idle.
      await act(async () => {
        emitStatus?.({
          claude: { status: 'degraded', readOnly: false },
          codex: { status: 'inactive', readOnly: false },
        })
      })

      // A usable Open control is exposed (cleanup-then-open), so recovery is one click away.
      await vi.waitFor(() => {
        const openButton = container.querySelector('button[aria-label="Open code assistant"]')
        expect(openButton).toBeTruthy()
        // Not an all-dead set (三态全灭): the Open trigger is genuinely clickable, not a stub.
        expect((openButton as HTMLButtonElement).disabled).toBe(false)
      })

      // It is the Open control, not the Attach/Close ("CLI running") dropdown.
      expect(container.querySelector('button[aria-label="Manage code assistant"]')).toBeNull()
    } finally {
      act(() => {
        root?.unmount()
      })
      root = null
      document.body.removeChild(container)
      ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
        previousReactActEnvironment
    }
  })

  it('test_lingering_keeps_a_close_control_instead_of_open', async () => {
    // 决议 2026-08-02 D-A2/D-A3 — `/exit` 之后 ah 的运行时(ahd + tmux server + 那块死窗格)
    // 都还在,只是没有活的 CLI 会话了。面板此时必须继续呈现管理控件(里面有 Close),而不是
    // 变回 `Open in CLI` —— 否则用户再点 Open 打开的就是那块死窗格。
    const previousReactActEnvironment = (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean })
      .IS_REACT_ACT_ENVIRONMENT
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    let emitStatus: ((status: unknown) => void) | null = null
    const unsubscribe = vi.fn()
    mocks.subscribeCodeAssistantStatus.mockImplementation(async (_workspaceRoot, onStatus) => {
      emitStatus = onStatus
      return unsubscribe
    })
    const container = document.createElement('div')
    document.body.appendChild(container)
    let root: Root | null = createRoot(container)

    try {
      await act(async () => {
        root?.render(React.createElement(CopilotPanel, {
          skillId: 'text-segmentation',
          copilot: mocks.useCopilot(),
          workspaceRoot: '/tmp/text-segmentation',
        }))
      })

      await act(async () => {
        emitStatus?.({
          claude: { status: 'lingering', readOnly: false },
          codex: { status: 'inactive', readOnly: false },
        })
      })

      await vi.waitFor(() => {
        const manageButton = container.querySelector('button[aria-label="Manage code assistant"]')
        expect(manageButton).toBeTruthy()
        expect((manageButton as HTMLButtonElement).disabled).toBe(false)
      })

      // 关键反向断言:不得回落到 Open 控件。
      expect(container.querySelector('button[aria-label="Open code assistant"]')).toBeNull()
    } finally {
      act(() => {
        root?.unmount()
      })
      root = null
      document.body.removeChild(container)
      ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
        previousReactActEnvironment
    }
  })

  it('shows the thinking indicator while an assistant turn is running with no text yet', () => {
    mocks.useCopilot.mockReturnValue(copilotState({
      messages: [
        { id: 'u1', role: 'user', content: 'hi', events: [], status: 'success', createdAt: 1 },
        { id: 'a1', role: 'assistant', content: '', events: [], status: 'running', createdAt: 2 },
      ],
    }))
    const html = renderToStaticMarkup(
      React.createElement(CopilotPanel, { skillId: 'text-segmentation', copilot: mocks.useCopilot() }),
    )
    expect(html).toContain('data-copilot-thinking="true"')
  })

  it('shows the thinking indicator in the pre-event gap (transcript ends on a user turn)', () => {
    mocks.useCopilot.mockReturnValue(copilotState({
      messages: [
        { id: 'u1', role: 'user', content: 'hi', events: [], status: 'success', createdAt: 1 },
      ],
    }))
    const html = renderToStaticMarkup(
      React.createElement(CopilotPanel, { skillId: 'text-segmentation', copilot: mocks.useCopilot() }),
    )
    expect(html).toContain('data-copilot-thinking="true"')
  })

  it('hides the thinking indicator once assistant text streams', () => {
    mocks.useCopilot.mockReturnValue(copilotState({
      messages: [
        { id: 'u1', role: 'user', content: 'hi', events: [], status: 'success', createdAt: 1 },
        { id: 'a1', role: 'assistant', content: 'partial answer', events: [], status: 'running', createdAt: 2 },
      ],
    }))
    const html = renderToStaticMarkup(
      React.createElement(CopilotPanel, { skillId: 'text-segmentation', copilot: mocks.useCopilot() }),
    )
    expect(html).not.toContain('data-copilot-thinking="true"')
  })

  it('renders chat messages as aligned message rows (assistant start-aligned)', () => {
    mocks.useCopilot.mockReturnValue(copilotState({
      messages: [
        {
          id: 'assistant-1',
          role: 'assistant',
          content: 'Streaming answer',
          events: [],
          status: 'running',
          createdAt: 1,
        },
      ],
    }))

    const html = renderToStaticMarkup(
      React.createElement(CopilotPanel, {
        skillId: 'text-segmentation',
        copilot: mocks.useCopilot(),
      }),
    )

    expect(html).toContain('data-copilot-message-role="assistant"')
    expect(html).toContain('data-slot="message"')
    expect(html).toContain('data-align="start"')
    expect(html).toContain('Streaming answer')
  })

  it('lifts judged refs to the parent after Ask Copilot Judge prepares context', async () => {
    const judged = {
      compare_result_ref: 'skill-1/golden/golden-1/compare/run-1/compare_result.json',
      judge_context_ref: 'skill-1/runs/run-1/copilot_judge/golden-1/judge_context.json',
      baseline_ref: 'skill-1/golden/golden-1/baseline.json',
      diff_summary: {
        baseline_id: 'golden-1',
        run_results_ref: 'skill-1/runs/run-1/result.json',
        total_score: 80,
        node_group_count: 1,
        failed_node_count: 1,
      },
    }
    mocks.prepareCopilotJudgeContext.mockResolvedValue(judged)
    const onJudgePrepared = vi.fn()

    renderToStaticMarkup(
      React.createElement(CopilotPanel, {
        skillId: 'skill-1',
        copilot: mocks.useCopilot(),
        view: 'eval',
        judgeRefs: {
          runResultsRef: 'skill-1/runs/run-1/result.json',
          baselineRef: 'skill-1/golden/golden-1/baseline.json',
        },
        onJudgePrepared,
      }),
    )

    const askButton = mocks.buttonProps.find((props) => props.children === 'Ask Copilot Judge')
    expect(askButton).toBeTruthy()

    ;(askButton?.onClick as (() => void) | undefined)?.()

    await vi.waitFor(() => {
      expect(mocks.prepareCopilotJudgeContext).toHaveBeenCalledWith('skill-1', {
        runResultsRef: 'skill-1/runs/run-1/result.json',
        baselineRef: 'skill-1/golden/golden-1/baseline.json',
      })
      expect(onJudgePrepared).toHaveBeenCalledWith(judged)
    })
  })

  it('clears prepared judge context when the user edits a normal follow-up draft', () => {
    const judged = {
      compare_result_ref: 'skill-1/golden/golden-1/compare/run-1/compare_result.json',
      judge_context_ref: 'skill-1/runs/run-1/copilot_judge/golden-1/judge_context.json',
      baseline_ref: 'skill-1/golden/golden-1/baseline.json',
      diff_summary: {
        baseline_id: 'golden-1',
        run_results_ref: 'skill-1/runs/run-1/result.json',
        total_score: 80,
        node_group_count: 1,
        failed_node_count: 1,
      },
    }
    const preparedDraft = buildCopilotJudgeDraft(judged)

    expect(nextDraftJudgeContext(preparedDraft, judged)).toEqual(judged)
    expect(nextDraftJudgeContext('plain follow-up question', judged)).toBeNull()
    expect(nextDraftJudgeContext(preparedDraft, judged, {
      skillId: 'skill-2',
      view: 'eval',
      judgeRefs: {
        runResultsRef: 'skill-1/runs/run-1/result.json',
        baselineRef: 'skill-1/golden/golden-1/baseline.json',
      },
    })).toBeNull()
    expect(nextDraftJudgeContext(preparedDraft, judged, {
      skillId: 'skill-1',
      view: 'edit',
      judgeRefs: {
        runResultsRef: 'skill-1/runs/run-1/result.json',
        baselineRef: 'skill-1/golden/golden-1/baseline.json',
      },
    })).toBeNull()
    expect(nextDraftJudgeContext(preparedDraft, judged, {
      skillId: 'skill-1',
      view: 'eval',
      judgeRefs: {
        runResultsRef: 'skill-1/runs/run-2/result.json',
        baselineRef: 'skill-1/golden/golden-1/baseline.json',
      },
    })).toBeNull()
  })

  it('maps backend transport failures to a localized copilot unavailable message', () => {
    expect(
      copilotBackendErrorMessage(new Error(BACKEND_UNAVAILABLE_MESSAGE), 'Copilot route config unavailable'),
    ).toBe('Copilot backend unavailable')
    expect(
      copilotBackendErrorMessage(new Error('different failure'), 'Copilot route config unavailable'),
    ).toBe('Copilot route config unavailable')
  })
})

function copilotState(overrides: Partial<{
  messages: CopilotMessage[]
}> = {}) {
  return {
    messages: overrides.messages ?? [],
    connectionStatus: 'open',
    reconnectInMs: null,
    lastError: null,
    sendMessage: vi.fn(),
    clearMessages: vi.fn(),
    persistenceError: null,
    activeSessionId: 'session-1',
    sessions: [],
    newSession: vi.fn(),
    switchSession: vi.fn(),
  }
}


describe('what a turn carries out of the composer', () => {
  beforeEach(() => {
    mocks.getRegistry.mockResolvedValue({ roles: {} })
    mocks.getRoles.mockResolvedValue({})
    mocks.useTemplates.mockReturnValue({ templates: [], templatesLoading: false })
    mocks.subscribeCodeAssistantStatus.mockResolvedValue(vi.fn())
    mocks.ensureCodeAssistantStatusEvents.mockResolvedValue(undefined)
    mocks.lastOpenedCodeAssistant.mockResolvedValue('claude')
    composerSeam.onChange = null
    composerSeam.onSend = null
    composerSeam.onImagesPasted = null
  })

  async function mountPanel(messages: CopilotMessage[] = []) {
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    const copilot = copilotState({ messages })
    mocks.useCopilot.mockReturnValue(copilot)
    // The fixture is the same partial controller the rest of this file uses; the
    // panel only reads the fields it sets.
    const controller = copilot as unknown as Parameters<typeof CopilotPanel>[0]['copilot']
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root: Root = createRoot(container)
    await act(async () => {
      root.render(React.createElement(CopilotPanel, {
        skillId: 'text-segmentation',
        copilot: controller,
        workspaceRoot: '/tmp/text-segmentation',
      }))
    })
    return { copilot, root, container }
  }

  it('sends the objects the user picked in THIS composer', async () => {
    // F4 ②: exactly what is in the composer rides along — the panel adds
    // nothing of its own, and drops nothing the user put there.
    const { copilot, root } = await mountPanel()
    const picked = [{ kind: 'phase', ref: 'chunking/segment', label: 'segment' }]

    act(() => composerSeam.onChange?.({ text: 'why is @segment slow?', mentions: picked }))
    await act(async () => composerSeam.onSend?.())

    expect(copilot.sendMessage).toHaveBeenCalledTimes(1)
    const [message, options] = copilot.sendMessage.mock.calls[0] as [
      string,
      { mentions?: unknown[] },
    ]
    expect(message).toBe('why is @segment slow?')
    expect(options.mentions).toEqual(picked)
    await act(async () => root.unmount())
  })

  it('carries a pasted image by value, with the message it was pasted into', async () => {
    // COPILOT_ASSIST-11: an image has no address to re-fetch it from, so its
    // bytes travel with the turn.
    const { copilot, root, container } = await mountPanel()
    const png = new File([new Uint8Array([1, 2, 3, 4])], 'shot.png', { type: 'image/png' })

    await act(async () => composerSeam.onImagesPasted?.([png]))
    expect(container.querySelector('[data-attachment-chip="shot.png"]')).toBeTruthy()

    act(() => composerSeam.onChange?.({ text: 'what is wrong here?', mentions: [] }))
    await act(async () => composerSeam.onSend?.())

    const [, options] = copilot.sendMessage.mock.calls[0] as [
      string,
      { attachments?: Array<{ media_type: string; name?: string }> },
    ]
    expect(options.attachments).toHaveLength(1)
    expect(options.attachments?.[0]).toMatchObject({ media_type: 'image/png', name: 'shot.png' })
    await act(async () => root.unmount())
  })

  it('treats a picture with no words as a real turn', async () => {
    // "What is wrong here?" is often the picture itself; requiring text as well
    // would grey the send button out on the commonest way people ask.
    const { copilot, root } = await mountPanel()
    const png = new File([new Uint8Array([9])], 'only.png', { type: 'image/png' })

    await act(async () => composerSeam.onImagesPasted?.([png]))
    await act(async () => composerSeam.onSend?.())

    expect(copilot.sendMessage).toHaveBeenCalledTimes(1)
    await act(async () => root.unmount())
  })

  it('leaves the pictures it carried on the turn that carried them', async () => {
    // Without this a picture-only question is a blank bubble in the history:
    // the bytes are deliberately not kept, so the turn has to say what went.
    const { root, container } = await mountPanel([
      {
        id: 'user-1',
        role: 'user',
        content: '',
        events: [],
        status: 'success',
        createdAt: 0,
        attachments: [{ mediaType: 'image/png', name: 'only.png', byteSize: 2048 }],
      },
    ])

    const chip = container.querySelector('[data-message-attachment="only.png"]')
    expect(chip?.textContent).toContain('only.png')
    expect(chip?.textContent).toContain('2 KB')
    await act(async () => root.unmount())
  })

  it('refuses a type the wire has no word for, and attaches nothing', async () => {
    const { root, container } = await mountPanel()
    const pdf = new File([new Uint8Array([1])], 'notes.pdf', { type: 'application/pdf' })

    await act(async () => composerSeam.onImagesPasted?.([pdf]))

    expect(container.querySelector('[data-attachment-chip="notes.pdf"]')).toBeNull()
    expect(toast.error).toHaveBeenCalled()
    await act(async () => root.unmount())
  })

  it('drops the images once the turn they belonged to has gone', async () => {
    const { copilot, root, container } = await mountPanel()
    copilot.sendMessage.mockReturnValue(true)
    const png = new File([new Uint8Array([1, 2])], 'shot.png', { type: 'image/png' })

    await act(async () => composerSeam.onImagesPasted?.([png]))
    act(() => composerSeam.onChange?.({ text: 'look', mentions: [] }))
    await act(async () => composerSeam.onSend?.())

    expect(container.querySelector('[data-attachment-tray]')).toBeNull()
    await act(async () => root.unmount())
  })

  it('sends nothing at all when the composer holds nothing', async () => {
    const { copilot, root } = await mountPanel()

    act(() => composerSeam.onChange?.({ text: '   ', mentions: [] }))
    await act(async () => composerSeam.onSend?.())

    expect(copilot.sendMessage).not.toHaveBeenCalled()
    await act(async () => root.unmount())
  })

  it('carries an empty mention list rather than inventing one', async () => {
    // A plain question is still a turn; it just names nothing.
    const { copilot, root } = await mountPanel()

    act(() => composerSeam.onChange?.({ text: 'hello', mentions: [] }))
    await act(async () => composerSeam.onSend?.())

    const [, options] = copilot.sendMessage.mock.calls[0] as [string, { mentions?: unknown[] }]
    expect(options.mentions).toEqual([])
    await act(async () => root.unmount())
  })
})

describe('buildGoldenDesignDraft (E3 entry①)', () => {
  it('asks for the node by name and points at the two documents the design names', () => {
    const draft = buildGoldenDesignDraft({ id: 'nodeA', label: 'Draft section' })

    expect(draft).toContain('Draft section')
    expect(draft).toContain('nodeA')
    expect(draft).toContain('GRAPH.md')
    expect(draft).toContain('SKILL.md')
  })

  it('tells copilot the schema is not the standard to design against', () => {
    const draft = buildGoldenDesignDraft({ id: 'nodeA' })

    expect(draft).toContain('不要把 input/output schema 当成黄金标准')
    expect(draft).toContain('谨慎')
  })

  it('falls back to the node id when the node has no label', () => {
    expect(buildGoldenDesignDraft({ id: 'nodeA' })).toContain('「nodeA」')
    expect(buildGoldenDesignDraft({ id: 'nodeA', label: '   ' })).toContain('「nodeA」')
  })
})
