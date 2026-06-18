import { afterEach, describe, expect, it, vi } from 'vitest'
import { AxiosError } from 'axios'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import {
  api,
  compileSkill,
  configureApiBaseURL,
  configureApiToken,
  createTestInput,
  deleteTestInput,
  getRelease,
  listReleases,
  prepareCopilotJudgeContext,
  postPredictRun,
  publishSkill,
  resolveCopilotBashApproval,
  saveGoldenBaseline,
  serializeSkillGraph,
  startRun,
  wsUrl,
} from './client'

const runtimeMocks = vi.hoisted(() => ({
  isTauriRuntime: vi.fn(() => false),
}))

const tauriMocks = vi.hoisted(() => ({
  readWorkspaceFile: vi.fn(),
  writeWorkspaceFile: vi.fn(),
  writeGoldenBaseline: vi.fn(),
  deleteWorkspacePath: vi.fn(),
}))

vi.mock('../config/runtime', () => runtimeMocks)

vi.mock('../lib/tauri', () => tauriMocks)

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
    runtimeMocks.isTauriRuntime.mockReturnValue(false)
    tauriMocks.readWorkspaceFile.mockReset()
    tauriMocks.writeWorkspaceFile.mockReset()
    tauriMocks.writeGoldenBaseline.mockReset()
    tauriMocks.deleteWorkspacePath.mockReset()
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
          artifact_ref: {
            artifact_id: 'text-segmentation',
            content_hash: `sha256:${'1'.repeat(64)}`,
            store: 'ephemeral',
            version: null,
            manifest_ref: 'file:///tmp/manifest.json',
            source_map_ref: 'file:///tmp/source_map.json',
          },
          source_map_ref: 'file:///tmp/source_map.json',
          execution_fingerprint: `sha256:${'2'.repeat(64)}`,
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
      artifact_ref: {
        artifact_id: 'text-segmentation',
        content_hash: `sha256:${'1'.repeat(64)}`,
        store: 'ephemeral',
        version: null,
        manifest_ref: 'file:///tmp/manifest.json',
        source_map_ref: 'file:///tmp/source_map.json',
      },
      source_map_ref: 'file:///tmp/source_map.json',
      execution_fingerprint: `sha256:${'2'.repeat(64)}`,
    })
  })

  it('reads release list and detail from product release endpoints', async () => {
    const release = {
      release_version: '1.0.0',
      artifact_id: 'text-segmentation',
      content_hash: `sha256:${'a'.repeat(64)}`,
      manifest_ref: 'manifests/text-segmentation.json',
      artifact_ref: {
        artifact_id: 'text-segmentation',
        content_hash: `sha256:${'a'.repeat(64)}`,
        manifest_ref: 'manifests/text-segmentation.json',
        store: 'product',
      },
      remote_sync: {
        status: 'skipped',
        reason: 'registry_not_configured',
      },
    }
    const seen: Array<{ method?: string; url?: string }> = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      seen.push({ method: config.method, url: config.url })
      return {
        data: config.url?.endsWith('/1.0.0') ? release : [release],
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(listReleases('text-segmentation')).resolves.toEqual([release])
    await expect(getRelease('text-segmentation', '1.0.0')).resolves.toEqual(release)
    expect(seen).toEqual([
      { method: 'get', url: '/skills/text-segmentation/releases' },
      { method: 'get', url: '/skills/text-segmentation/releases/1.0.0' },
    ])
  })

  it('publish result type exposes release identity and remote sync state', async () => {
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      expect(config.method).toBe('post')
      expect(config.url).toBe('/skills/text-segmentation/publish')
      return {
        data: {
          status: 'ok',
          message: 'Published to local product store',
          artifact_id: 'text-segmentation',
          extra: {
            release_version: '1.0.0',
            artifact_id: 'text-segmentation',
            content_hash: `sha256:${'a'.repeat(64)}`,
            manifest_ref: 'manifests/text-segmentation.json',
            artifact_ref: {
              artifact_id: 'text-segmentation',
              content_hash: `sha256:${'a'.repeat(64)}`,
              manifest_ref: 'manifests/text-segmentation.json',
              store: 'product',
            },
            remote_sync: {
              status: 'skipped',
              reason: 'registry_not_configured',
            },
          },
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(publishSkill('text-segmentation')).resolves.toMatchObject({
      extra: {
        release_version: '1.0.0',
        artifact_id: 'text-segmentation',
        content_hash: `sha256:${'a'.repeat(64)}`,
        manifest_ref: 'manifests/text-segmentation.json',
        artifact_ref: { store: 'product' },
        remote_sync: {
          status: 'skipped',
          reason: 'registry_not_configured',
        },
      },
    })
  })

  it('test_predict_and_run_requests_do_not_send_source_paths', async () => {
    const seen: Array<{ url?: string; body: unknown }> = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      const body = config.data ? JSON.parse(String(config.data)) : null
      seen.push({ url: config.url, body })
      return {
        data: config.url?.endsWith('/predict')
          ? { run_id: 'predict-run', status: 'success' }
          : {
              run_id: 'run-1',
              status: 'running',
              started_at: '2026-06-17T00:00:00Z',
              metrics: null,
              input_summary: null,
            },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await postPredictRun('text-segmentation', { topic: 'mars' })
    await startRun('text-segmentation', { topic: 'mars' })

    expect(seen).toEqual([
      {
        url: '/skills/text-segmentation/runs/predict',
        body: { input_data: { topic: 'mars' } },
      },
      {
        url: '/skills/text-segmentation/runs',
        body: { input_data: { topic: 'mars' } },
      },
    ])
    for (const request of seen) {
      expect(JSON.stringify(request.body)).not.toContain('skill_path')
      expect(JSON.stringify(request.body)).not.toContain('source_path')
    }
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

  it('surfaces backend unavailable for compile network failures', async () => {
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      throw new AxiosError('Network Error', 'ERR_NETWORK', config)
    }

    await expect(compileSkill('broken')).rejects.toThrow('Backend unavailable')
  })

  it('surfaces backend unavailable for run network failures', async () => {
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      throw new AxiosError('connect ECONNREFUSED 127.0.0.1:8787', 'ECONNREFUSED', config)
    }

    await expect(startRun('text-segmentation', { topic: 'mars' })).rejects.toThrow('Backend unavailable')
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

  it('posts Copilot Bash approval decisions to the safe-write endpoint', async () => {
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      expect(config.method).toBe('post')
      expect(config.url).toBe('/skills/text-segmentation/copilot/bash-approval')
      expect(JSON.parse(String(config.data))).toEqual({
        tool_use_id: 'tu-approve',
        approve: true,
      })
      return {
        data: {
          tool_use_id: 'tu-approve',
          approved: true,
          executed: true,
          success: true,
          stdout: 'ok\n',
          stderr: '',
          returncode: 0,
          message: null,
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(
      resolveCopilotBashApproval('text-segmentation', {
        toolUseId: 'tu-approve',
        approve: true,
      }),
    ).resolves.toEqual({
      tool_use_id: 'tu-approve',
      approved: true,
      executed: true,
      success: true,
      stdout: 'ok\n',
      stderr: '',
      returncode: 0,
      message: null,
    })
  })

  it('prepares Copilot Judge context with explicit golden refs', async () => {
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      expect(config.method).toBe('post')
      expect(config.url).toBe('/skills/text-segmentation/copilot/judge')
      expect(JSON.parse(String(config.data))).toEqual({
        run_results_ref: 'text-segmentation/runs/run-1/result.json',
        baseline_ref: 'text-segmentation/golden/golden-1/baseline.json',
      })
      return {
        data: {
          compare_result_ref: 'text-segmentation/golden/golden-1/compare/run-1/compare_result.json',
          judge_context_ref: 'text-segmentation/runs/run-1/copilot_judge/golden-1/judge_context.json',
          baseline_ref: 'text-segmentation/golden/golden-1/baseline.json',
          diff_summary: {
            baseline_id: 'golden-1',
            run_results_ref: 'text-segmentation/runs/run-1/result.json',
            total_score: 88,
            node_group_count: 2,
            failed_node_count: 1,
          },
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(
      prepareCopilotJudgeContext('text-segmentation', {
        runResultsRef: 'text-segmentation/runs/run-1/result.json',
        baselineRef: 'text-segmentation/golden/golden-1/baseline.json',
      }),
    ).resolves.toEqual({
      compare_result_ref: 'text-segmentation/golden/golden-1/compare/run-1/compare_result.json',
      judge_context_ref: 'text-segmentation/runs/run-1/copilot_judge/golden-1/judge_context.json',
      baseline_ref: 'text-segmentation/golden/golden-1/baseline.json',
      diff_summary: {
        baseline_id: 'golden-1',
        run_results_ref: 'text-segmentation/runs/run-1/result.json',
        total_score: 88,
        node_group_count: 2,
        failed_node_count: 1,
      },
    })
  })

  it('writes new test inputs through native fs in Tauri', async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(true)
    tauriMocks.readWorkspaceFile.mockRejectedValue(new Error('file not found: case.json'))
    tauriMocks.writeWorkspaceFile.mockResolvedValue({
      path: '.workspace/test_inputs/case.json',
      hash: 'native-hash',
    })
    const requests: Array<{ method?: string; url?: string }> = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      requests.push({ method: config.method, url: config.url })
      return {
        data: {},
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    const metadata = await createTestInput('skill-a', 'case', { x: 1 })

    expect(tauriMocks.writeWorkspaceFile).toHaveBeenCalledWith(
      'skill-a',
      '.workspace/test_inputs/case.json',
      '{\n  "x": 1\n}',
      null,
      { createIfAbsent: true },
    )
    expect(tauriMocks.readWorkspaceFile).not.toHaveBeenCalled()
    expect(requests).toEqual([])
    expect(metadata).toMatchObject({
      id: 'case',
      name: 'case',
      size_bytes: 12,
      content_preview: '{"x":1}',
    })
    expect(new Date(metadata.created_at).toString()).not.toBe('Invalid Date')
  })

  it('writes golden result refs through native fs in Tauri after backend planning', async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(true)
    tauriMocks.writeWorkspaceFile.mockResolvedValue({
      path: '.workspace/golden/run-1/baseline.json',
      hash: 'golden-hash',
    })
    const requests: Array<{ method?: string; url?: string; data?: unknown }> = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      requests.push({
        method: config.method,
        url: config.url,
        data: config.data ? JSON.parse(String(config.data)) : undefined,
      })
      return {
        data: {
          baseline: {
            id: 'run-1',
            source_run_id: 'run-1',
            source_run_results_ref: 'skill-a/runs/run-1/result.json',
            baseline_ref: '.workspace/golden/run-1/baseline.json',
            linked_input_id: 'run-1',
            created_at: '2026-06-16T00:00:00Z',
            locked: false,
            content_path: '/workspace/.workspace/golden/run-1/baseline.json',
          },
          files: [
            {
              path: '.workspace/golden/run-1/baseline.json',
              content: '{"baseline_id":"run-1"}',
            },
            {
              path: '.workspace/golden/run-1/report.json',
              content: '{"case_count":1}',
            },
            {
              path: '.workspace/golden/run-1/cases/setup.json',
              content: '{"expected_output":{"ok":true}}',
            },
          ],
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(saveGoldenBaseline('skill-a', 'run-1', false)).resolves.toEqual({
      id: 'run-1',
      source_run_id: 'run-1',
      source_run_results_ref: 'skill-a/runs/run-1/result.json',
      baseline_ref: '.workspace/golden/run-1/baseline.json',
      linked_input_id: 'run-1',
      created_at: '2026-06-16T00:00:00Z',
      locked: false,
      content_path: '/workspace/.workspace/golden/run-1/baseline.json',
    })

    expect(requests).toEqual([
      {
        method: 'post',
        url: '/skills/skill-a/golden/plan',
        data: { run_id: 'run-1', lock: false },
      },
    ])
    expect(tauriMocks.writeWorkspaceFile).toHaveBeenNthCalledWith(
      1,
      'skill-a',
      '.workspace/golden/run-1/baseline.json',
      '{"baseline_id":"run-1"}',
      null,
      { createIfAbsent: true },
    )
    expect(tauriMocks.writeWorkspaceFile).toHaveBeenNthCalledWith(
      2,
      'skill-a',
      '.workspace/golden/run-1/report.json',
      '{"case_count":1}',
      null,
      { createIfAbsent: true },
    )
    expect(tauriMocks.writeWorkspaceFile).toHaveBeenNthCalledWith(
      3,
      'skill-a',
      '.workspace/golden/run-1/cases/setup.json',
      '{"expected_output":{"ok":true}}',
      null,
      { createIfAbsent: true },
    )
    expect(tauriMocks.writeGoldenBaseline).not.toHaveBeenCalled()
  })

  it('plans imported local-workspace golden promotion by API skill id and writes to the absolute root', async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(true)
    tauriMocks.writeWorkspaceFile.mockResolvedValue({
      path: '.workspace/golden/run-1/baseline.json',
      hash: 'golden-hash',
    })
    const requests: Array<{ method?: string; url?: string; data?: unknown }> = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      requests.push({
        method: config.method,
        url: config.url,
        data: config.data ? JSON.parse(String(config.data)) : undefined,
      })
      return {
        data: {
          baseline: {
            id: 'run-1',
            source_run_id: 'run-1',
            source_run_results_ref: 'skill-a/runs/run-1/result.json',
            baseline_ref: '.workspace/golden/run-1/baseline.json',
            linked_input_id: 'run-1',
            created_at: '2026-06-16T00:00:00Z',
            locked: false,
            content_path: '/workspace/.workspace/golden/run-1/baseline.json',
          },
          files: [
            {
              path: '.workspace/golden/run-1/baseline.json',
              content: '{"baseline_id":"run-1"}',
            },
            {
              path: '.workspace/golden/run-1/report.json',
              content: '{"case_count":1}',
            },
            {
              path: '.workspace/golden/run-1/cases/setup.json',
              content: '{"expected_output":{"ok":true}}',
            },
          ],
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(
      saveGoldenBaseline('skill-a', 'run-1', false, '/abs/path'),
    ).resolves.toMatchObject({
      id: 'run-1',
      linked_input_id: 'run-1',
    })

    expect(requests).toEqual([
      {
        method: 'post',
        url: '/skills/skill-a/golden/plan',
        data: { run_id: 'run-1', lock: false },
      },
    ])
    expect(tauriMocks.writeWorkspaceFile).toHaveBeenNthCalledWith(
      1,
      '/abs/path',
      '.workspace/golden/run-1/baseline.json',
      '{"baseline_id":"run-1"}',
      null,
      { createIfAbsent: true },
    )
    expect(tauriMocks.writeWorkspaceFile).toHaveBeenNthCalledWith(
      2,
      '/abs/path',
      '.workspace/golden/run-1/report.json',
      '{"case_count":1}',
      null,
      { createIfAbsent: true },
    )
    expect(tauriMocks.writeWorkspaceFile).toHaveBeenNthCalledWith(
      3,
      '/abs/path',
      '.workspace/golden/run-1/cases/setup.json',
      '{"expected_output":{"ok":true}}',
      null,
      { createIfAbsent: true },
    )
    expect(tauriMocks.writeGoldenBaseline).not.toHaveBeenCalled()
  })

  it('writes imported local-workspace test inputs to the absolute root with no-clobber', async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(true)
    tauriMocks.writeWorkspaceFile.mockResolvedValue({
      path: '.workspace/test_inputs/case.json',
      hash: 'native-hash',
    })
    const selection = `local-workspace:${encodeURIComponent('skill-a')}:${encodeURIComponent('/Users/sevenx/Projects/imported-skill')}`

    await expect(createTestInput(selection, 'case', { x: 1 })).resolves.toMatchObject({
      id: 'case',
      name: 'case',
    })

    expect(tauriMocks.writeWorkspaceFile).toHaveBeenCalledWith(
      '/Users/sevenx/Projects/imported-skill',
      '.workspace/test_inputs/case.json',
      '{\n  "x": 1\n}',
      null,
      { createIfAbsent: true },
    )
    expect(tauriMocks.readWorkspaceFile).not.toHaveBeenCalled()
  })

  it('rejects duplicate test input names from native no-clobber without pre-reading', async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(true)
    tauriMocks.writeWorkspaceFile.mockRejectedValue(new Error('file already exists: .workspace/test_inputs/case.json'))

    await expect(createTestInput('skill-a', 'case', { x: 1 })).rejects.toThrow(
      'file already exists',
    )

    expect(tauriMocks.readWorkspaceFile).not.toHaveBeenCalled()
    expect(tauriMocks.writeWorkspaceFile).toHaveBeenCalledWith(
      'skill-a',
      '.workspace/test_inputs/case.json',
      '{\n  "x": 1\n}',
      null,
      { createIfAbsent: true },
    )
  })

  it('deletes test inputs through native fs in Tauri', async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(true)
    tauriMocks.deleteWorkspacePath.mockResolvedValue(undefined)
    const requests: Array<{ method?: string; url?: string }> = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      requests.push({ method: config.method, url: config.url })
      return {
        data: {},
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await deleteTestInput('skill-a', 'case')

    expect(tauriMocks.deleteWorkspacePath).toHaveBeenCalledWith(
      'skill-a',
      '.workspace/test_inputs/case.json',
    )
    expect(requests).toEqual([])
  })

  it('rejects unsafe test input names before native fs writes in Tauri', async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(true)
    const requests: Array<{ method?: string; url?: string }> = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      requests.push({ method: config.method, url: config.url })
      return {
        data: {},
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(createTestInput('skill-a', '../case', { x: 1 })).rejects.toThrow(
      'Invalid test input name',
    )
    await expect(deleteTestInput('skill-a', '-leading')).rejects.toThrow(
      'Invalid test input name',
    )

    expect(tauriMocks.writeWorkspaceFile).not.toHaveBeenCalled()
    expect(tauriMocks.deleteWorkspacePath).not.toHaveBeenCalled()
    expect(requests).toEqual([])
  })

  it('keeps HTTP create and delete outside Tauri', async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(false)
    const requests: Array<{ method?: string; url?: string; data?: unknown; fallbackHeader?: string }> = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      requests.push({
        method: config.method,
        url: config.url,
        data: config.data ? JSON.parse(String(config.data)) : undefined,
        fallbackHeader: String(config.headers.get('X-Studio-Write-Fallback') ?? ''),
      })
      return {
        data: {
          id: 'case',
          name: 'case',
          created_at: '2026-06-16T00:00:00Z',
          size_bytes: 12,
          content_preview: '{"x":1}',
        },
        status: config.method === 'delete' ? 204 : 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(createTestInput('skill-a', 'case', { x: 1 })).resolves.toEqual({
      id: 'case',
      name: 'case',
      created_at: '2026-06-16T00:00:00Z',
      size_bytes: 12,
      content_preview: '{"x":1}',
    })
    await deleteTestInput('skill-a', 'case')

    expect(requests).toEqual([
      {
        method: 'post',
        url: '/skills/skill-a/test_inputs',
        data: { name: 'case', content: { x: 1 } },
        fallbackHeader: 'browser',
      },
      {
        method: 'delete',
        url: '/skills/skill-a/test_inputs/case',
        data: undefined,
        fallbackHeader: 'browser',
      },
    ])
    expect(tauriMocks.writeWorkspaceFile).not.toHaveBeenCalled()
    expect(tauriMocks.deleteWorkspacePath).not.toHaveBeenCalled()
  })

  it('marks HTTP golden promotion outside Tauri as browser fallback', async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(false)
    const requests: Array<{ method?: string; url?: string; data?: unknown; fallbackHeader?: string }> = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      requests.push({
        method: config.method,
        url: config.url,
        data: config.data ? JSON.parse(String(config.data)) : undefined,
        fallbackHeader: String(config.headers.get('X-Studio-Write-Fallback') ?? ''),
      })
      return {
        data: {
          id: 'run-1',
          source_run_id: 'run-1',
          source_run_results_ref: 'skill-a/runs/run-1/result.json',
          baseline_ref: '.workspace/golden/run-1/baseline.json',
          linked_input_id: 'run-1',
          created_at: '2026-06-16T00:00:00Z',
          locked: false,
          content_path: '/workspace/.workspace/golden/run-1/baseline.json',
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(saveGoldenBaseline('skill-a', 'run-1', true)).resolves.toMatchObject({
      id: 'run-1',
      locked: false,
    })

    expect(requests).toEqual([
      {
        method: 'post',
        url: '/skills/skill-a/golden',
        data: { run_id: 'run-1', lock: true },
        fallbackHeader: 'browser',
      },
    ])
    expect(tauriMocks.writeGoldenBaseline).not.toHaveBeenCalled()
  })
})
