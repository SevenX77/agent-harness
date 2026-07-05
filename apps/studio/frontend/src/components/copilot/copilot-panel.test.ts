import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CopilotMessage } from '../../types/copilot'
import { buildCopilotJudgeDraft, copilotBackendErrorMessage, CopilotPanel, isComposerSendKey, nextDraftJudgeContext } from './copilot-panel'
import { BACKEND_UNAVAILABLE_MESSAGE } from '@/utils/errors'

const mocks = vi.hoisted(() => ({
  useCopilot: vi.fn(),
  useTemplates: vi.fn(),
  getRegistry: vi.fn(),
  getRoles: vi.fn(),
  prepareCopilotJudgeContext: vi.fn(),
  openClaudeCode: vi.fn(),
  openCodexCli: vi.fn(),
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

vi.mock('../../hooks/useTemplates', () => ({
  useTemplates: mocks.useTemplates,
}))

vi.mock('../../lib/tauri', () => ({
  openClaudeCode: mocks.openClaudeCode,
  openCodexCli: mocks.openCodexCli,
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

  it('opens the current workspace through the Claude/Codex assistant menu', async () => {
    const html = renderToStaticMarkup(
      React.createElement(CopilotPanel, {
        skillId: 'text-segmentation',
        copilot: mocks.useCopilot(),
        workspaceRoot: '/tmp/text-segmentation',
      }),
    )

    const openButton = mocks.buttonProps.find((props) => props['aria-label'] === 'Open code assistant')
    expect(openButton).toBeTruthy()
    expect(html).toContain('Claude')
    expect(html).toContain('Codex')

    const menuText = (props: Record<string, unknown>) =>
      renderToStaticMarkup(React.createElement(React.Fragment, null, props.children as React.ReactNode))
    const claudeItem = mocks.menuItemProps.find((props) => menuText(props).includes('Claude'))
    const codexItem = mocks.menuItemProps.find((props) => menuText(props).includes('Codex'))
    expect(claudeItem).toBeTruthy()
    expect(codexItem).toBeTruthy()

    ;(claudeItem?.onSelect as (() => void) | undefined)?.()

    await vi.waitFor(() => {
      expect(mocks.openClaudeCode).toHaveBeenCalledWith('/tmp/text-segmentation')
    })

    ;(codexItem?.onSelect as (() => void) | undefined)?.()

    await vi.waitFor(() => {
      expect(mocks.openCodexCli).toHaveBeenCalledWith('/tmp/text-segmentation')
    })
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
