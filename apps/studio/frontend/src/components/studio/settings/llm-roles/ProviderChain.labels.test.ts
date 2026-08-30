import { describe, expect, it } from 'vitest'
import type { ProviderModelOption, RolesData } from '@/api/llm'
import { chainEntries } from './ProviderChain'

/**
 * A role's fallback chain shows every route it holds, named so they can be told
 * apart.
 *
 * Before this, `collapseProviderEntries` kept the best-ranked entry per provider
 * NAME and hid the rest — routes the reader had配置 into the chain, that the
 * gateway would really try, invisible in the one place that claims to list them.
 * 00_settings-ux-spec.md §2.1:「聚合只发生在**展示**层，配置与执行永远面向 route
 * 全集」, and the chain IS the configuration.
 */

function providerModel(overrides: Partial<ProviderModelOption> & { route_id: string }): ProviderModelOption {
  return {
    endpoint_id: overrides.route_id.split(':')[0],
    provider_label: 'Qiniu',
    provider_kind: 'third_party',
    provider_model_id: 'deepseek-v4-flash',
    base_url: 'https://api.qnaigc.com/v1',
    protocol: 'openai_compatible',
    ui_state: 'ready',
    capability_state: 'known',
    capabilities: {},
    ...overrides,
  } as ProviderModelOption
}

const data: RolesData = {
  models: {},
  providers: {},
  roles: {},
}

describe('chainEntries', () => {
  it('keeps every configured route, in the order the chain runs them', () => {
    const providers = [
      'qiniu-openai:deepseek-v4-flash',
      'qiniu-anthropic:deepseek-v4-flash',
      'ark-official:deepseek-v4-flash',
    ]
    const models = new Map(providers.map((routeId) => [
      routeId,
      providerModel({
        route_id: routeId,
        provider_label: routeId.startsWith('ark') ? 'Ark Official' : 'Qiniu',
      }),
    ]))

    expect(chainEntries(providers, data, models).map((entry) => entry.providerCode)).toEqual(providers)
  })

  it('names same-provider routes by their transport, so the chain is choosable', () => {
    const models = new Map([
      ['qiniu-openai:m', providerModel({
        route_id: 'qiniu-openai:m',
        base_url: 'https://api.qnaigc.com/v1',
        protocol: 'openai_compatible',
      })],
      ['qiniu-anthropic:m', providerModel({
        route_id: 'qiniu-anthropic:m',
        base_url: 'https://anthropic.qnaigc.com',
        protocol: 'anthropic_compatible',
      })],
    ])

    const labels = chainEntries(['qiniu-openai:m', 'qiniu-anthropic:m'], data, models)
      .map((entry) => entry.label)

    expect(labels).toEqual(['Qiniu · api.qnaigc · OpenAI-compatible', 'Qiniu · anthropic.qnaigc · Anthropic-compatible'])
  })

  it('still names a route the registry no longer lists', () => {
    // A chain entry whose route was deleted from the registry is exactly the
    // entry a reader most needs to find, so it keeps a name — its own id.
    const entries = chainEntries(['gone:m'], data, new Map())

    expect(entries.map((entry) => entry.label)).toEqual(['gone:m'])
  })

  it('prefers the name the role itself stored for a provider', () => {
    // `data.providers[code].name` is what the role wrote down when the route was
    // added; the registry's label can drift, and the chain is the role's record.
    const withName: RolesData = {
      ...data,
      providers: { 'qiniu-openai:m': { name: 'Qiniu (my key)', type: 'openai_compatible' } },
    }

    expect(chainEntries(['qiniu-openai:m'], withName, new Map()).map((entry) => entry.label))
      .toEqual(['Qiniu (my key)'])
  })
})
