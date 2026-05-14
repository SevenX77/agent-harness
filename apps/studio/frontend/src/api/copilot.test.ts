import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './client'
import {
  getCopilotCredentials,
  testCopilotCredentials,
  updateCopilotCredentials,
  type CopilotCredentials,
} from './copilot'

vi.mock('./client', () => ({
  api: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
  },
}))

const credentials: CopilotCredentials = {
  active_backend: 'claude',
  backends: {
    claude: { has_key: true, last4: '1234', base_url: '' },
    deepseek: { has_key: false, last4: null, base_url: 'https://deepseek.example' },
    gemini: { has_key: false, last4: null, base_url: '' },
    openai: { has_key: false, last4: null, base_url: '' },
  },
}

describe('copilot credentials api', () => {
  afterEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.put).mockReset()
    vi.mocked(api.post).mockReset()
  })

  it('passes through last4 and base_url from GET credentials', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ data: credentials })

    await expect(getCopilotCredentials()).resolves.toEqual(credentials)
    expect(api.get).toHaveBeenCalledWith('/copilot/credentials')
  })

  it('passes base_url through PUT credentials', async () => {
    vi.mocked(api.put).mockResolvedValueOnce({ data: credentials })

    await updateCopilotCredentials('deepseek', 'sk-key', false, 'https://deepseek.example')

    expect(api.put).toHaveBeenCalledWith('/copilot/credentials', {
      backend: 'deepseek',
      api_key: 'sk-key',
      set_active: false,
      base_url: 'https://deepseek.example',
    })
  })

  it('tests candidate credentials successfully', async () => {
    const result = { status: 'ok' as const, latency_ms: 42, model_seen: 'claude-sonnet' }
    vi.mocked(api.post).mockResolvedValueOnce({ data: result })

    await expect(
      testCopilotCredentials({
        backend: 'claude',
        api_key: 'sk-test',
        base_url: '',
      }),
    ).resolves.toEqual(result)
    expect(api.post).toHaveBeenCalledWith('/copilot/credentials/test', {
      backend: 'claude',
      api_key: 'sk-test',
      base_url: '',
    })
  })

  it('propagates 4xx errors with response status information', async () => {
    const error = { response: { status: 400, data: { status: 'invalid_key' } } }
    vi.mocked(api.post).mockRejectedValueOnce(error)

    await expect(
      testCopilotCredentials({
        backend: 'openai',
        api_key: 'bad-key',
      }),
    ).rejects.toMatchObject({ response: { status: 400 } })
  })
})
