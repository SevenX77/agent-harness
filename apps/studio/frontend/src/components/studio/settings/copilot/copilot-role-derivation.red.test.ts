/**
 * WS-5 RED: Copilot role derivation from real registry DTO.
 *
 * Replaces the mock/name-heuristic logic in `mock-copilot-data.ts`
 * (`buildCopilotRolesFromRealData` + `isClaudeAgentSdkCompatibleRoute`) with a
 * pure, tested derivation module. Contracts (settings-ux-spec §3.0/§3.2/§3.5):
 *
 *  - Candidate visibility (#3/#7): untested routes stay visible; eligibility is
 *    backend capability/protocol, not a frontend name guess.
 *  - Dynamic default ladder (#2): Claude prefers opus 4.8 then 4.7; DeepSeek
 *    prefers V4 Pro then V3.2 Pro; a missing family surfaces NO fake default.
 *  - `copilot_` role key (#5 / PM edge 2): selecting a model group keeps the
 *    `copilot_*` role key — it must never be rewritten to the bare group id.
 *
 * RED today: `copilot-role-derivation` does not exist; the inline CopilotTab
 * `selectModelGroup` rewrites `copilot_*` -> bare `modelGroupId`.
 */
import { describe, expect, it } from 'vitest'
import type { CredentialsState, ModelGroup, RolesData } from '@/api/llm'
import {
  applyCopilotModelGroupSelection,
  deriveCopilotCandidateGroups,
  pickDefaultCopilotGroupIds,
} from './copilot-role-derivation'

function anthropicCredentials(): CredentialsState {
  return {
    providers: [
      { id: 'anthropic-official', name: 'Anthropic Official', api_key: 'sk', provider_type: 'anthropic', last_test_status: 'ok' },
      { id: 'deepseek-official', name: 'DeepSeek Official', api_key: 'sk', provider_type: 'anthropic_compatible', last_test_status: 'ok' },
    ],
  } as unknown as CredentialsState
}

function group(canonicalId: string, displayName: string, route: {
  routeId: string
  endpointId: string
  providerLabel: string
  uiState: string
}): ModelGroup {
  return {
    canonical_id: canonicalId,
    display_name: displayName,
    provider_models: [
      {
        route_id: route.routeId,
        endpoint_id: route.endpointId,
        provider_label: route.providerLabel,
        provider_kind: 'official',
        provider_model_id: canonicalId,
        ui_state: route.uiState,
        capability_state: route.uiState === 'ready' ? 'known' : 'unknown',
        capabilities: {},
      },
    ],
    status_summary: { ready: route.uiState === 'ready' ? 1 : 0, historical_ready: 0, untested: route.uiState === 'untested' ? 1 : 0, failed: 0, cooling_down: 0, off: 0 },
    capability_summary: { capability_known_count: 0, thinking: 'unknown', tools: 'unknown', structured_output: 'unknown' },
  } as unknown as ModelGroup
}

describe('deriveCopilotCandidateGroups (candidate visibility)', () => {
  it('keeps an untested Anthropic-compatible route as a selectable candidate', () => {
    const groups = [
      group('claude-opus-4.8', 'Claude Opus 4.8', {
        routeId: 'anthropic-official:claude-opus-4.8',
        endpointId: 'anthropic-official',
        providerLabel: 'Anthropic Official',
        uiState: 'untested',
      }),
    ]

    const candidates = deriveCopilotCandidateGroups(groups, anthropicCredentials())
    const claude = candidates.find((candidate) => candidate.id === 'claude-opus-4.8')

    expect(claude).toBeDefined()
    expect(claude!.routes.map((route) => route.route_id)).toContain(
      'anthropic-official:claude-opus-4.8',
    )
  })
})

describe('pickDefaultCopilotGroupIds (dynamic default ladder)', () => {
  function candidatesFrom(groups: ModelGroup[]) {
    return deriveCopilotCandidateGroups(groups, anthropicCredentials())
  }

  it('prefers Claude opus 4.8 over 4.7 and DeepSeek V4 Pro over V3.2 Pro', () => {
    const groups = [
      group('claude-opus-4.7', 'Claude Opus 4.7', { routeId: 'anthropic-official:claude-opus-4.7', endpointId: 'anthropic-official', providerLabel: 'Anthropic Official', uiState: 'ready' }),
      group('claude-opus-4.8', 'Claude Opus 4.8', { routeId: 'anthropic-official:claude-opus-4.8', endpointId: 'anthropic-official', providerLabel: 'Anthropic Official', uiState: 'ready' }),
      group('deepseek-v3.2-pro', 'DeepSeek V3.2 Pro', { routeId: 'deepseek-official:deepseek-v3.2-pro', endpointId: 'deepseek-official', providerLabel: 'DeepSeek Official', uiState: 'ready' }),
      group('deepseek-v4-pro', 'DeepSeek V4 Pro', { routeId: 'deepseek-official:deepseek-v4-pro', endpointId: 'deepseek-official', providerLabel: 'DeepSeek Official', uiState: 'ready' }),
    ]

    const defaults = pickDefaultCopilotGroupIds(candidatesFrom(groups))

    expect(defaults).toContain('claude-opus-4.8')
    expect(defaults).not.toContain('claude-opus-4.7')
    expect(defaults).toContain('deepseek-v4-pro')
    expect(defaults).not.toContain('deepseek-v3.2-pro')
  })

  it('does not invent a default when the family is missing', () => {
    const groups = [
      group('claude-opus-4.7', 'Claude Opus 4.7', { routeId: 'anthropic-official:claude-opus-4.7', endpointId: 'anthropic-official', providerLabel: 'Anthropic Official', uiState: 'ready' }),
    ]

    const defaults = pickDefaultCopilotGroupIds(candidatesFrom(groups))

    // Claude falls back to 4.7 (best available), but no DeepSeek family present.
    expect(defaults).toContain('claude-opus-4.7')
    expect(defaults.some((id) => id.startsWith('deepseek'))).toBe(false)
  })
})

describe('applyCopilotModelGroupSelection (copilot_ role key)', () => {
  it('keeps the copilot_ role key after selecting a model group', () => {
    const roles = {
      roles: {
        copilot_custom_1: {
          role_kind: 'copilot',
          system_prompt_prefix: '',
          model_fallback_enabled: true,
          fallback_chain: [],
          intent: { provider_preference: 'manual_order' },
          model_groups: [],
          active_model: '',
          models: {},
        },
      },
    } as unknown as RolesData

    const next = applyCopilotModelGroupSelection(roles, 'copilot_custom_1', 'claude-opus-4.8')

    expect(Object.keys(next.roles)).toContain('copilot_custom_1')
    expect(Object.keys(next.roles)).not.toContain('claude-opus-4.8')
    expect(next.roles.copilot_custom_1.role_kind).toBe('copilot')
  })
})
