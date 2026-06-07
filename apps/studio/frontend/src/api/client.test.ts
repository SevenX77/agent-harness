import { afterEach, describe, expect, it, vi } from 'vitest'
import { AxiosError } from 'axios'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { api, compileSkill, configureApiBaseURL, configureApiToken, serializeSkillGraph, writeSkillFile, wsUrl } from './client'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))


function captureHeadersAdapter(assertConfig: (config: InternalAxiosRequestConfig) => void): AxiosAdapter {
  return async (config): Promise<AxiosResponse> => {
    assertConfig(config)
    return {
      data: {},
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    }
  }
}

describe('api client auth token', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    api.defaults.adapter = undefined
    configureApiBaseURL('http://localhost:8787/api')
    configureApiToken(null)
  })

  it('test_no_token_no_auth_header', async () => {
    configureApiToken(null)

    await api.get('/probe', {
      adapter: captureHeadersAdapter((config) => {
        expect(config.headers.get('Authorization')).toBeUndefined()
      }),
    })
  })

  it('test_with_token_auth_header_set', async () => {
    configureApiToken('abc')

    await api.get('/probe', {
      adapter: captureHeadersAdapter((config) => {
        expect(config.headers.get('Authorization')).toBe('Bearer abc')
      }),
    })
  })

  it('test_ws_url_without_token_has_no_query', () => {
    vi.stubGlobal('window', { location: { origin: 'http://localhost' } })
    configureApiBaseURL('/api')

    expect(wsUrl('/ws/events')).toBe('ws://localhost/ws/events')
  })

  it('test_ws_url_appends_configured_token', () => {
    vi.stubGlobal('window', { location: { origin: 'http://localhost' } })
    configureApiBaseURL('/api')
    configureApiToken('xyz')

    expect(wsUrl('/ws/events')).toBe('ws://localhost/ws/events?token=xyz')
  })

  it('test_ws_url_appends_token_after_existing_query', () => {
    vi.stubGlobal('window', { location: { origin: 'http://localhost' } })
    configureApiBaseURL('/api')
    configureApiToken('a b')

    expect(wsUrl('/ws/events?cursor=1')).toBe('ws://localhost/ws/events?cursor=1&token=a%20b')
  })

  it('test_compile_skill_posts_to_compile_endpoint', async () => {
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      expect(config.method).toBe('post')
      expect(config.url).toBe('/skills/text-segmentation/compile')
      return {
        data: {
          skill_id: 'text-segmentation',
          status: 'ok',
          phase_count: 1,
          manifest_name: 'text-segmentation',
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(compileSkill('text-segmentation')).resolves.toEqual({
      skill_id: 'text-segmentation',
      status: 'ok',
      phase_count: 1,
      manifest_name: 'text-segmentation',
    })
  })

  it('test_compile_skill_returns_structured_compile_failure', async () => {
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      const response: AxiosResponse = {
        data: {
          code: 'compile_failed',
          detail: 'Skill compilation failed with 1 error',
          errors: [{
            file: 'GRAPH.md',
            line: 3,
            field: null,
            severity: 'fatal',
            message: 'Invalid phase reference',
          }],
        },
        status: 422,
        statusText: 'Unprocessable Entity',
        headers: {},
        config,
      }
      throw new AxiosError('Request failed', 'ERR_BAD_REQUEST', config, null, response)
    }

    await expect(compileSkill('broken')).resolves.toEqual({
      code: 'compile_failed',
      detail: 'Skill compilation failed with 1 error',
      errors: [{
        file: 'GRAPH.md',
        line: 3,
        field: null,
        severity: 'fatal',
        message: 'Invalid phase reference',
      }],
    })
  })

  it('test_serialize_skill_graph_posts_phase_refs_to_serializer_endpoint', async () => {
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      expect(config.method).toBe('post')
      expect(config.url).toBe('/skills/text-segmentation/graph/serialize')
      expect(JSON.parse(String(config.data))).toEqual({
        phases: [{
          id: 'agent',
          src: 'phases/agent',
          depends_on: ['logic'],
          mode: 'skill',
        }],
        expected_hash: 'abc123',
      })
      return {
        data: {
          markdown_content: '---\nname: text-segmentation\n---\n',
          phase_count: 1,
          elapsed_ms: 1.5,
          current_hash: 'def456',
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(serializeSkillGraph('text-segmentation', [{
      id: 'agent',
      src: 'phases/agent',
      depends_on: ['logic'],
      mode: 'skill',
    }], 'abc123')).resolves.toEqual({
      markdown_content: '---\nname: text-segmentation\n---\n',
      phase_count: 1,
      elapsed_ms: 1.5,
      current_hash: 'def456',
    })
  })

  it('test_local_file_write_does_not_use_fastapi_file_write_endpoint', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    const { invoke } = await import('@tauri-apps/api/core')
    vi.mocked(invoke).mockResolvedValue({
      path: 'GRAPH.md',
      hash: 'mock-hash',
    })

    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      throw new Error(`FastAPI local file writer should be retired: ${config.method} ${config.url}`)
    }

    await expect(writeSkillFile('text-segmentation', 'GRAPH.md', '---\nname: text\n---\n', 'abc123'))
      .resolves.toEqual(expect.objectContaining({
        path: 'GRAPH.md',
        hash: expect.any(String),
      }))
  })

  it('test_tauri_hash_conflict_is_converted_to_axios_409_with_remote_content', async () => {
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} })
    const { invoke } = await import('@tauri-apps/api/core')
    vi.mocked(invoke).mockRejectedValue({
      type: 'HashConflict',
      data: {
        current_hash: 'remote-hash',
        current_content: 'remote markdown\n',
      },
    })

    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      throw new Error(`FastAPI local file writer should not handle native conflicts: ${config.method} ${config.url}`)
    }

    await expect(writeSkillFile('/Users/sevenx/Projects/writer-smoke', 'GRAPH.md', 'local markdown\n', 'stale-hash'))
      .rejects.toMatchObject({
        response: {
          status: 409,
          data: {
            current_hash: 'remote-hash',
            current_markdown_content: 'remote markdown\n',
          },
        },
      })
  })
})
