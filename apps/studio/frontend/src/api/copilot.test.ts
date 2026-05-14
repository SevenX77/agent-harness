import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './client'
import {
  getCopilotCredentials,
  putCopilotCredentials,
  testCopilotProvider,
  type CopilotCredentials,
  type TestProviderResponse,
} from './copilot'

vi.mock('./client', () => ({
  api: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
  },
}))

const credentials: CopilotCredentials = {
  active_provider_id: 'default-claude',
  providers: [
    {
      id: 'default-claude',
      name: 'Claude',
      kind: 'anthropic',
      api_key: 'sk-claude',
      base_url: '',
      active_model_id: 'claude-sonnet-4-5',
    },
    {
      id: 'default-openai',
      name: 'OpenAI',
      kind: 'openai-compat',
      api_key: '',
      base_url: 'https://openai.example/v1',
      active_model_id: null,
    },
  ],
}

describe('copilot provider api', () => {
  afterEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.put).mockReset()
    vi.mocked(api.post).mockReset()
  })

  it('passes plaintext provider credentials through GET', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ data: credentials })

    await expect(getCopilotCredentials()).resolves.toEqual(credentials)
    expect(api.get).toHaveBeenCalledWith('/copilot/credentials')
  })

  it('PUTs the full credentials object', async () => {
    vi.mocked(api.put).mockResolvedValueOnce({ data: credentials })

    await expect(putCopilotCredentials(credentials)).resolves.toBeUndefined()

    expect(api.put).toHaveBeenCalledWith('/copilot/credentials', credentials)
  })

  it('tests a provider and passes discovered models through', async () => {
    const result: TestProviderResponse = {
      status: 'ok',
      latency_ms: 42,
      models: [
        { id: 'claude-sonnet-4-5', supports_thinking: true, supports_vision: true },
        { id: 'claude-haiku-4-5', supports_thinking: false, supports_vision: true },
      ],
      message: null,
    }
    vi.mocked(api.post).mockResolvedValueOnce({ data: result })

    await expect(
      testCopilotProvider({
        id: 'default-claude',
        name: 'Claude',
        kind: 'anthropic',
        api_key: 'sk-test',
        base_url: '',
      }),
    ).resolves.toEqual(result)
    expect(api.post).toHaveBeenCalledWith('/copilot/providers/test', {
      id: 'default-claude',
      name: 'Claude',
      kind: 'anthropic',
      api_key: 'sk-test',
      base_url: '',
    })
  })

  it('propagates 4xx errors with response status information', async () => {
    const error = { response: { status: 400, data: { status: 'invalid_key' } } }
    vi.mocked(api.post).mockRejectedValueOnce(error)

    await expect(
      testCopilotProvider({
        id: 'default-openai',
        name: 'OpenAI',
        kind: 'openai-compat',
        api_key: 'bad-key',
        base_url: '',
      }),
    ).rejects.toMatchObject({ response: { status: 400 } })
  })
})
