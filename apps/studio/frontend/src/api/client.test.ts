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
  fetchGoldenContent,
  getCommunityCatalogConfig,
  getRelease,
  getRoleTestResults,
  getResumeValidity,
  getTruthSources,
  importIoIntoWorkspace,
  invalidateRoleTestResultsCache,
  listReleases,
  prepareCopilotJudgeContext,
  postPredictRun,
  publishSkill,
  interruptCopilot,
  resolveCopilotToolApproval,
  resumeRun,
  saveGoldenBaseline,
  saveManualGolden,
  serializeSkillGraph,
  startRun,
  writeSkillFile,
  wsUrl,
  resetClientReadCachesForTests,
} from './client'

const runtimeMocks = vi.hoisted(() => ({
  isTauriRuntime: vi.fn(() => false),
}))

const tauriMocks = vi.hoisted(() => ({
  readWorkspaceFile: vi.fn(),
  writeWorkspaceFile: vi.fn(),
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
    tauriMocks.deleteWorkspacePath.mockReset()
    resetClientReadCachesForTests()
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

  it('dedupes settings read-only bootstrap endpoints', async () => {
    const seen: string[] = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      seen.push(`${config.method} ${config.url}`)
      await Promise.resolve()
      return {
        data: config.url === '/system/truth-sources'
          ? { sections: [] }
          : { manifest_url: 'https://example.test/manifest.json', signing_pubkey: 'pub' },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await Promise.all([getTruthSources(), getTruthSources()])
    await Promise.all([getCommunityCatalogConfig(), getCommunityCatalogConfig()])
    await getTruthSources()
    await getCommunityCatalogConfig()

    expect(seen).toEqual([
      'get /system/truth-sources',
      'get /system/community-catalog-config',
    ])
  })

  it('dedupes role test result seed reads and refreshes after explicit invalidation', async () => {
    const seen: string[] = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      seen.push(`${config.method} ${config.url}`)
      await Promise.resolve()
      return {
        data: { results: {} },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await Promise.all([getRoleTestResults(), getRoleTestResults()])
    await getRoleTestResults()
    invalidateRoleTestResultsCache()
    await getRoleTestResults()

    expect(seen).toEqual([
      'get /llm/roles/test-results',
      'get /llm/roles/test-results',
    ])
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

  it('posts node-scoped IO imports with the selected phase id', async () => {
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      expect(config.method).toBe('post')
      expect(config.url).toBe('/skills/skill-a/io/import')
      expect(JSON.parse(String(config.data))).toEqual({
        path: '/tmp/material',
        name: 'material',
        node_id: 'segment',
      })
      return {
        data: { dir: 'import_files/segment/material', entries: [] },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(importIoIntoWorkspace('skill-a', '/tmp/material', {
      name: 'material',
      nodeId: 'segment',
    })).resolves.toEqual({ dir: 'import_files/segment/material', entries: [] })
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

  it('preserves request diagnostics for backend-unavailable failures', async () => {
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      throw new AxiosError('connect ECONNREFUSED 127.0.0.1:8787', 'ECONNREFUSED', config)
    }

    await expect(startRun('text-segmentation', { topic: 'mars' })).rejects.toMatchObject({
      name: 'BackendUnavailableError',
      message: 'Backend unavailable',
      axiosCode: 'ECONNREFUSED',
      originalMessage: 'connect ECONNREFUSED 127.0.0.1:8787',
      requestMethod: 'POST',
      requestPath: '/skills/text-segmentation/runs',
      requestBaseURL: 'http://localhost:8787/api',
      requestURL: 'http://localhost:8787/api/skills/text-segmentation/runs',
    })
  })

  it('test_resume_run_posts_checkpoint_node_target_and_structured_human_response', async () => {
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      expect(config.method).toBe('post')
      expect(config.url).toBe('/skills/text-segmentation/runs/run-123/resume')
      expect(JSON.parse(String(config.data))).toEqual({
        checkpoint_id: 'checkpoint-review',
        checkpoint_ns: 'agent:review',
        resume_from_node_id: 'review',
        resume_to_node_id: 'final',
        context_overrides: { draft: 'manual' },
        human_input: null,
        human_response: { content: 'approved', tool_call_id: 'tool-1' },
      })
      return {
        data: {
          run_id: 'run-123',
          status: 'success',
          started_at: '2026-06-17T00:00:00Z',
          input_summary: 'resumed',
          metrics: null,
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await resumeRun('text-segmentation', 'run-123', {
      checkpointId: 'checkpoint-review',
      checkpointNs: 'agent:review',
      resumeFromNodeId: 'review',
      resumeToNodeId: 'final',
      contextOverrides: { draft: 'manual' },
      humanResponse: { content: 'approved', toolCallId: 'tool-1' },
    })
  })

  it('test_resume_validity_posts_checkpoint_node_target_without_source_paths', async () => {
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      expect(config.method).toBe('post')
      expect(config.url).toBe('/skills/text-segmentation/runs/run-123/resume/validity')
      const body = JSON.parse(String(config.data))
      expect(body).toEqual({
        checkpoint_id: 'checkpoint-review',
        checkpoint_ns: 'agent:review',
        resume_from_node_id: 'review',
        resume_to_node_id: 'final',
      })
      expect(JSON.stringify(body)).not.toContain('source_path')
      expect(JSON.stringify(body)).not.toContain('skill_path')
      return {
        data: {
          run_id: 'run-123',
          resume_allowed: false,
          reason: 'dirty_upstream',
          checkpoint_id: 'checkpoint-review',
          checkpoint_ns: 'agent:review',
          resume_from_node_id: 'review',
          resume_to_node_id: 'final',
          dirty_fields: ['execution_fingerprint'],
          snapshot_content_hash: `sha256:${'1'.repeat(64)}`,
          current_content_hash: `sha256:${'2'.repeat(64)}`,
          snapshot_execution_fingerprint: `sha256:${'3'.repeat(64)}`,
          current_execution_fingerprint: `sha256:${'4'.repeat(64)}`,
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(getResumeValidity('text-segmentation', 'run-123', {
      checkpointId: 'checkpoint-review',
      checkpointNs: 'agent:review',
      resumeFromNodeId: 'review',
      resumeToNodeId: 'final',
    })).resolves.toMatchObject({
      resume_allowed: false,
      reason: 'dirty_upstream',
      dirty_fields: ['execution_fingerprint'],
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
          output: true,
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
      output: true,
      mode: 'skill',
    }], 'abc123')).resolves.toEqual({
      markdown_content: '---\nname: text-segmentation\n---\n',
      phase_count: 1,
      elapsed_ms: 1.5,
      current_hash: 'def456',
    })
  })

  it('serializeSkillGraph sends workspace_root for a drilled subgraph path', async () => {
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      expect(config.url).toBe('/skills/text-segmentation/graph/serialize')
      expect(JSON.parse(String(config.data))).toEqual({
        phases: [{ id: 'setup', src: 'phases/setup', depends_on: [] }],
        expected_hash: 'abc123',
        workspace_root: '/abs/story/subgraph/text-segmentation',
      })
      return {
        data: { markdown_content: '', phase_count: 1, elapsed_ms: 1, current_hash: 'def456' },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await serializeSkillGraph(
      'text-segmentation',
      [{ id: 'setup', src: 'phases/setup', depends_on: [], output: false, mode: 'logic' }],
      'abc123',
      '/abs/story/subgraph/text-segmentation',
    )
  })

  it('browser writeSkillFile marks FastAPI writes as explicit fallback', async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(false)
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      expect(config.method).toBe('post')
      expect(config.url).toBe('/skills/text-segmentation/files/GRAPH.md')
      expect(config.headers.get('X-Studio-Write-Fallback')).toBe('browser')
      expect(JSON.parse(String(config.data))).toEqual({
        content: 'next graph',
        expected_hash: 'old-hash',
      })
      return {
        data: { path: 'GRAPH.md', hash: 'next-hash' },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(
      writeSkillFile('text-segmentation', 'GRAPH.md', 'next graph', 'old-hash'),
    ).resolves.toEqual({ path: 'GRAPH.md', hash: 'next-hash' })
  })

  it('posts Copilot tool approval decisions to the approval endpoint', async () => {
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      expect(config.method).toBe('post')
      expect(config.url).toBe('/skills/text-segmentation/copilot/tool-approval')
      expect(JSON.parse(String(config.data))).toEqual({
        tool_use_id: 'tu-approve',
        approve: true,
      })
      return {
        data: {
          tool_use_id: 'tu-approve',
          approved: true,
          resolved: true,
          message: null,
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(
      resolveCopilotToolApproval('text-segmentation', {
        toolUseId: 'tu-approve',
        approve: true,
      }),
    ).resolves.toEqual({
      tool_use_id: 'tu-approve',
      approved: true,
      resolved: true,
      message: null,
    })
  })

  it('posts a Copilot interrupt to the interrupt endpoint', async () => {
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      expect(config.method).toBe('post')
      expect(config.url).toBe('/skills/text-segmentation/copilot/interrupt')
      return {
        data: { interrupted: true },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(interruptCopilot('text-segmentation')).resolves.toEqual({ interrupted: true })
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
      path: '.workspace/import_files/case.json',
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
      '.workspace/import_files/case.json',
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
  })

  it('writes imported local-workspace test inputs to the absolute root with no-clobber', async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(true)
    tauriMocks.writeWorkspaceFile.mockResolvedValue({
      path: '.workspace/import_files/case.json',
      hash: 'native-hash',
    })
    const selection = `local-workspace:${encodeURIComponent('skill-a')}:${encodeURIComponent('/Users/sevenx/Projects/imported-skill')}`

    await expect(createTestInput(selection, 'case', { x: 1 })).resolves.toMatchObject({
      id: 'case',
      name: 'case',
    })

    expect(tauriMocks.writeWorkspaceFile).toHaveBeenCalledWith(
      '/Users/sevenx/Projects/imported-skill',
      '.workspace/import_files/case.json',
      '{\n  "x": 1\n}',
      null,
      { createIfAbsent: true },
    )
    expect(tauriMocks.readWorkspaceFile).not.toHaveBeenCalled()
  })

  it('rejects duplicate test input names from native no-clobber without pre-reading', async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(true)
    tauriMocks.writeWorkspaceFile.mockRejectedValue(new Error('file already exists: .workspace/import_files/case.json'))

    await expect(createTestInput('skill-a', 'case', { x: 1 })).rejects.toThrow(
      'file already exists',
    )

    expect(tauriMocks.readWorkspaceFile).not.toHaveBeenCalled()
    expect(tauriMocks.writeWorkspaceFile).toHaveBeenCalledWith(
      'skill-a',
      '.workspace/import_files/case.json',
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
      '.workspace/import_files/case.json',
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
  })

  it('includes node_id in the browser golden request for a per-node promote (atom #32)', async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(false)
    const requests: Array<{ url?: string; data?: unknown }> = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      requests.push({
        url: config.url,
        data: config.data ? JSON.parse(String(config.data)) : undefined,
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

    await saveGoldenBaseline('skill-a', 'run-1', false, null, 'draft')

    expect(requests).toEqual([
      {
        url: '/skills/skill-a/golden',
        data: { run_id: 'run-1', lock: false, node_id: 'draft' },
      },
    ])
  })

  it('omits node_id from the request when no node is given (run-level baseline)', async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(false)
    const requests: Array<{ data?: unknown }> = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      requests.push({ data: config.data ? JSON.parse(String(config.data)) : undefined })
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

    await saveGoldenBaseline('skill-a', 'run-1', false)

    expect(requests[0].data).toEqual({ run_id: 'run-1', lock: false })
    expect(requests[0].data).not.toHaveProperty('node_id')
  })

  it('threads node_id into the Tauri golden plan request for a per-node promote', async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(true)
    tauriMocks.writeWorkspaceFile.mockResolvedValue({
      path: '.workspace/golden/run-1/baseline.json',
      hash: 'golden-hash',
    })
    const requests: Array<{ url?: string; data?: unknown }> = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      requests.push({
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
            { path: '.workspace/golden/run-1/baseline.json', content: '{"baseline_id":"run-1"}' },
          ],
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await saveGoldenBaseline('skill-a', 'run-1', false, '/abs/path', 'draft')

    expect(requests).toEqual([
      {
        url: '/skills/skill-a/golden/plan',
        data: { run_id: 'run-1', lock: false, node_id: 'draft' },
      },
    ])
  })

  it('writes a manual golden through native fs in Tauri after backend planning', async () => {
    runtimeMocks.isTauriRuntime.mockReturnValue(true)
    tauriMocks.writeWorkspaceFile.mockResolvedValue({
      path: '.workspace/golden/segment/baseline.json',
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
            id: 'segment',
            source_run_id: null,
            source_run_results_ref: null,
            baseline_ref: '.workspace/golden/segment/baseline.json',
            linked_input_id: 'segment',
            created_at: '2026-06-16T00:00:00Z',
            locked: false,
            content_path: '/workspace/.workspace/golden/segment/baseline.json',
            cases: [
              {
                case_id: 'segment',
                node_id: 'segment',
                phase_id: 'segment',
                expected_output_ref: 'cases/segment.json',
              },
            ],
          },
          files: [
            {
              path: '.workspace/golden/segment/baseline.json',
              content: '{"baseline_id":"segment"}',
            },
            {
              path: '.workspace/golden/segment/report.json',
              content: '{"case_count":1}',
            },
            {
              path: '.workspace/golden/segment/cases/segment.json',
              content: '{"expected_output":{"segments":[]}}',
            },
          ],
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(saveManualGolden('skill-a', 'segment', { segments: [] })).resolves.toMatchObject({
      id: 'segment',
      source_run_id: null,
      linked_input_id: 'segment',
    })

    expect(requests).toEqual([
      {
        method: 'post',
        url: '/skills/skill-a/golden/manual/plan',
        data: { node_id: 'segment', expected_output: { segments: [] } },
      },
    ])
    expect(tauriMocks.writeWorkspaceFile).toHaveBeenNthCalledWith(
      1,
      'skill-a',
      '.workspace/golden/segment/baseline.json',
      '{"baseline_id":"segment"}',
      null,
      { createIfAbsent: true },
    )
    expect(tauriMocks.writeWorkspaceFile).toHaveBeenNthCalledWith(
      2,
      'skill-a',
      '.workspace/golden/segment/report.json',
      '{"case_count":1}',
      null,
      { createIfAbsent: true },
    )
    expect(tauriMocks.writeWorkspaceFile).toHaveBeenNthCalledWith(
      3,
      'skill-a',
      '.workspace/golden/segment/cases/segment.json',
      '{"expected_output":{"segments":[]}}',
      null,
      { createIfAbsent: true },
    )
  })

  it('degrades the manual golden write to Desktop-only off-desktop with no Python disk-write', async () => {
    // D12: the manual golden write is Rust-sole-writer only. It always asks the backend
    // for the plan (read-only, no disk write) and then writes each file through the Rust
    // native-fs writer. Outside the desktop runtime writeWorkspaceFile throws "Desktop
    // only" and nothing persists (the MVP1 desktop-first web boundary). There is NO
    // browser HTTP disk-write fallback and NO X-Studio-Write-Fallback header.
    runtimeMocks.isTauriRuntime.mockReturnValue(false)
    tauriMocks.writeWorkspaceFile.mockRejectedValue(new Error('Desktop only'))
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
          baseline: {
            id: 'segment',
            source_run_id: null,
            source_run_results_ref: null,
            baseline_ref: '.workspace/golden/segment/baseline.json',
            linked_input_id: 'segment',
            created_at: '2026-06-16T00:00:00Z',
            locked: false,
            content_path: '/workspace/.workspace/golden/segment/baseline.json',
            cases: [],
          },
          files: [
            {
              path: '.workspace/golden/segment/baseline.json',
              content: '{"baseline_id":"segment"}',
            },
          ],
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(saveManualGolden('skill-a', 'segment', { segments: [] })).rejects.toThrow(
      'Desktop only',
    )

    // Only the plan endpoint (no disk write, no browser-fallback header) is hit; the
    // Python disk-write endpoint /golden/manual is never called.
    expect(requests).toEqual([
      {
        method: 'post',
        url: '/skills/skill-a/golden/manual/plan',
        data: { node_id: 'segment', expected_output: { segments: [] } },
        fallbackHeader: '',
      },
    ])
    // The Rust writer was attempted and degraded (threw) — nothing persisted via HTTP.
    expect(tauriMocks.writeWorkspaceFile).toHaveBeenCalledTimes(1)
  })

  it('reads golden baseline content for editing (atom #29) without a node filter', async () => {
    const requests: Array<{ method?: string; url?: string; params?: unknown }> = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      requests.push({ method: config.method, url: config.url, params: config.params })
      return {
        data: {
          id: 'run-1',
          source_run_id: 'run-1',
          locked: false,
          cases: [
            {
              case_id: 'segment',
              node_id: 'segment',
              phase_id: 'segment',
              expected_output: { segments: ['a', 'b'] },
            },
          ],
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await expect(fetchGoldenContent('skill-a', 'run-1')).resolves.toEqual({
      id: 'run-1',
      source_run_id: 'run-1',
      locked: false,
      cases: [
        {
          case_id: 'segment',
          node_id: 'segment',
          phase_id: 'segment',
          expected_output: { segments: ['a', 'b'] },
        },
      ],
    })

    // GET to the content endpoint; no node_id param when none is given.
    expect(requests).toEqual([
      {
        method: 'get',
        url: '/skills/skill-a/golden/run-1/content',
        params: undefined,
      },
    ])
  })

  it('scopes golden content to a single node via the node_id query param (atom #29)', async () => {
    const requests: Array<{ url?: string; params?: unknown }> = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      requests.push({ url: config.url, params: config.params })
      return {
        data: {
          id: 'run-1',
          source_run_id: 'run-1',
          locked: true,
          cases: [
            {
              case_id: 'segment',
              node_id: 'segment',
              phase_id: 'segment',
              expected_output: { segments: [] },
            },
          ],
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await fetchGoldenContent('skill-a', 'run-1', 'segment')

    expect(requests).toEqual([
      {
        url: '/skills/skill-a/golden/run-1/content',
        params: { node_id: 'segment' },
      },
    ])
  })
})
