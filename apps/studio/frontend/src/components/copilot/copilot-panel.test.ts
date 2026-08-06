// @vitest-environment jsdom

import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CopilotMessage } from '../../types/copilot'
import {
  buildCopilotJudgeDraft,
  codeAssistantAttachMenuLabels,
  codeAssistantCloseButtonLabel,
  codeAssistantPendingLabel,
  copilotBackendErrorMessage,
  CopilotPanel,
  isComposerSendKey,
  nextDraftJudgeContext,
} from './copilot-panel'
import { BACKEND_UNAVAILABLE_MESSAGE } from '@/utils/errors'

const mocks = vi.hoisted(() => ({
  useCopilot: vi.fn(),
  useTemplates: vi.fn(),
  getRegistry: vi.fn(),
  getRoles: vi.fn(),
  prepareCopilotJudgeContext: vi.fn(),
  openClaudeCode: vi.fn(),
  openCodexCli: vi.fn(),
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

vi.mock('../../hooks/useCopilot', () => ({
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
    expect(isComposerSendKey({ key: 'Enter', shiftKey: false, nativeEvent: { isComposing: false } })).toBe(true)
  })

  it('keeps Shift+Enter as a line break', () => {
    expect(isComposerSendKey({ key: 'Enter', shiftKey: true, nativeEvent: { isComposing: false } })).toBe(false)
  })

  it('never sends while an IME composition is active', () => {
    expect(isComposerSendKey({ key: 'Enter', shiftKey: false, nativeEvent: { isComposing: true } })).toBe(false)
  })

  it('ignores other keys', () => {
    expect(isComposerSendKey({ key: 'a', shiftKey: false, nativeEvent: { isComposing: false } })).toBe(false)
  })
})

describe('buildCopilotJudgeDraft', () => {
  beforeEach(() => {
    mocks.getRegistry.mockResolvedValue({ roles: {} })
    mocks.getRoles.mockResolvedValue({})
    mocks.prepareCopilotJudgeContext.mockReset()
    mocks.openClaudeCode.mockReset()
    mocks.openClaudeCode.mockResolvedValue(true)
    mocks.openCodexCli.mockReset()
    mocks.openCodexCli.mockResolvedValue(true)
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
    // 决议 2026-08-05 D-F2/F-5 —— Open 下拉里有 "Resume Claude code",点击走与 Open
    // 同一条启动流程,但以 resume 语义调用(openClaudeCode 收到
    // { resumeLastConversation: true });普通 Open 不带该语义。仅 claude 有此项。
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
    expect(codeAssistantCloseButtonLabel({ claude: inactive, codex: inactive })).toBeNull()
    expect(codeAssistantCloseButtonLabel({ claude: active, codex: inactive })).toBe('Close Claude code')
    expect(codeAssistantCloseButtonLabel({ claude: inactive, codex: active })).toBe('Close Codex')
    expect(codeAssistantCloseButtonLabel({ claude: active, codex: active })).toBe('Close assistants')
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

    expect(codeAssistantCloseButtonLabel({ claude: lingering, codex: inactive })).toBe('Close Claude code')
    expect(codeAssistantCloseButtonLabel({ claude: inactive, codex: lingering })).toBe('Close Codex')
    expect(codeAssistantCloseButtonLabel({ claude: lingering, codex: active })).toBe('Close assistants')

    expect(codeAssistantAttachMenuLabels({ claude: lingering, codex: inactive })).toEqual([
      'Attach Claude code (exited)',
    ])
    // 对照组:活会话不带后缀 —— 证明后缀是按相位算出来的,不是常量。
    expect(codeAssistantAttachMenuLabels({ claude: lingering, codex: active })).toEqual([
      'Attach Claude code (exited)',
      'Attach Codex',
    ])
    expect(codeAssistantAttachMenuLabels({ claude: inactive, codex: inactive })).toEqual([])
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
    expect(codeAssistantAttachMenuLabels({ claude: inactive, codex: inactive })).toEqual([])
    expect(codeAssistantAttachMenuLabels({ claude: active, codex: inactive })).toEqual(['Attach Claude code'])
    expect(codeAssistantAttachMenuLabels({ claude: inactive, codex: active })).toEqual(['Attach Codex'])
    expect(codeAssistantAttachMenuLabels({ claude: active, codex: active })).toEqual(['Attach Claude code', 'Attach Codex'])
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

    expect(codeAssistantPendingLabel({ claude: unknown, codex: unknown })).toBe('Checking…')
    expect(codeAssistantPendingLabel({ claude: starting, codex: inactive })).toBe('Starting…')
    expect(codeAssistantPendingLabel({ claude: unknown, codex: starting })).toBe('Starting…')
    // 对照组:没有任何进行中的相位就没有进行态控件。
    expect(codeAssistantPendingLabel({ claude: inactive, codex: inactive })).toBeNull()
    expect(codeAssistantPendingLabel({ claude: active, codex: inactive })).toBeNull()
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

    expect(codeAssistantCloseButtonLabel({ claude: unknown, codex: unknown })).toBeNull()
    expect(codeAssistantAttachMenuLabels({ claude: unknown, codex: unknown })).toEqual([])
    // 对照组:另一侧真的在跑时,只有它进这两类。
    expect(codeAssistantCloseButtonLabel({ claude: unknown, codex: active })).toBe('Close Codex')
    expect(codeAssistantAttachMenuLabels({ claude: unknown, codex: active })).toEqual(['Attach Codex'])
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
