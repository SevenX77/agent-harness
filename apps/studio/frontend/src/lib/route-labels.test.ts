import { describe, expect, it } from 'vitest'
import { distinguishingRouteLabels, hostLabel, transportLabel } from './route-labels'

function route(overrides: Partial<Parameters<typeof distinguishingRouteLabels>[0][number]> & { route_id: string }) {
  return {
    endpoint_id: overrides.route_id.split(':')[0],
    provider_label: 'Qiniu',
    provider_model_id: 'deepseek-v4-flash',
    base_url: 'https://api.qnaigc.example/v1',
    protocol: 'openai_compatible' as const,
    ...overrides,
  }
}

describe('hostLabel', () => {
  it('keeps the part of the host a reader recognises', () => {
    expect(hostLabel('https://api.qnaigc.com/v1')).toBe('api.qnaigc')
    expect(hostLabel('https://anthropic.qnaigc.com')).toBe('anthropic.qnaigc')
  })

  it('leaves a bare host or an address alone', () => {
    expect(hostLabel('http://localhost:8000/v1')).toBe('localhost:8000')
    expect(hostLabel('http://127.0.0.1:1234/v1')).toBe('127.0.0.1:1234')
  })

  it('hands back what it was given when that is not a URL at all', () => {
    expect(hostLabel('qiniu-openai')).toBe('qiniu-openai')
  })
})

describe('transportLabel', () => {
  // J-01.L (批示轮三 R3-10): the first name is the provider's identity (its
  // host); the protocol FAMILY is a trailing annotation. The old order put
  // "OpenAI" first on a DeepSeek card, which reads as the wrong vendor.
  it('names the host first and annotates the protocol family after it', () => {
    expect(transportLabel('openai_compatible', 'https://api.qnaigc.com/v1')).toBe('api.qnaigc · OpenAI-compatible')
    expect(transportLabel('anthropic_compatible', 'https://anthropic.qnaigc.com')).toBe('anthropic.qnaigc · Anthropic-compatible')
  })

  it('never leads with the protocol family on an official vendor host', () => {
    expect(transportLabel('openai_compatible', 'https://api.deepseek.com')).toBe('api.deepseek · OpenAI-compatible')
  })
})

describe('distinguishingRouteLabels', () => {
  it('says only the provider name when that already tells them apart', () => {
    const labels = distinguishingRouteLabels([
      route({ route_id: 'qiniu-openai:m', provider_label: 'Qiniu' }),
      route({ route_id: 'openrouter:m', provider_label: 'OpenRouter' }),
    ])

    expect(labels.get('qiniu-openai:m')).toBe('Qiniu')
    expect(labels.get('openrouter:m')).toBe('OpenRouter')
  })

  it('adds the transport to the ones that share a provider name', () => {
    // The measured case (2026-08-21): `Qiniu` seven times in one dropdown, with
    // nothing on screen to choose by.
    const labels = distinguishingRouteLabels([
      route({ route_id: 'qiniu-openai:m' }),
      route({
        route_id: 'qiniu-anthropic:m',
        protocol: 'anthropic_compatible',
        base_url: 'https://anthropic.qnaigc.example',
      }),
    ])

    expect(labels.get('qiniu-openai:m')).toBe('Qiniu · api.qnaigc · OpenAI-compatible')
    expect(labels.get('qiniu-anthropic:m')).toBe('Qiniu · anthropic.qnaigc · Anthropic-compatible')
  })

  it('adds the model id when the transport is the same and the model is not', () => {
    const labels = distinguishingRouteLabels([
      route({ route_id: 'qiniu-openai:flash', provider_model_id: 'deepseek-v4-flash' }),
      route({ route_id: 'qiniu-openai:flash-260425', provider_model_id: 'deepseek-v4-flash-260425' }),
    ])

    expect(labels.get('qiniu-openai:flash')).toBe('Qiniu · deepseek-v4-flash')
    expect(labels.get('qiniu-openai:flash-260425')).toBe('Qiniu · deepseek-v4-flash-260425')
  })

  it('names only what differs, so a shared field never becomes noise', () => {
    // Both are OpenAI on the same host; saying so twice would push the one
    // thing that DOES differ off the end of a truncated row.
    const labels = distinguishingRouteLabels([
      route({ route_id: 'a:flash', provider_model_id: 'flash' }),
      route({ route_id: 'a:pro', provider_model_id: 'pro' }),
    ])

    expect([...labels.values()].every((label) => !label.includes('OpenAI'))).toBe(true)
  })

  it('never hands back two identical labels, whatever the input', () => {
    // The postcondition the whole function exists for. Two routes that agree on
    // every readable field still get told apart — by the one thing that is
    // unique by construction.
    const labels = distinguishingRouteLabels([
      route({ route_id: 'a:m', endpoint_id: 'a' }),
      route({ route_id: 'b:m', endpoint_id: 'b' }),
    ])

    expect(new Set(labels.values()).size).toBe(2)
  })

  it('falls back to the endpoint and then the route when there is no provider name', () => {
    const labels = distinguishingRouteLabels([
      route({ route_id: 'a:m', provider_label: '   ', endpoint_id: 'a' }),
      route({ route_id: 'b:m', provider_label: '', endpoint_id: '' }),
    ])

    expect(labels.get('a:m')).toBe('a')
    expect(labels.get('b:m')).toBe('b:m')
  })
})
