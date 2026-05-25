import { afterEach, describe, expect, it } from 'vitest'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { api } from './client'
import {
  applyModelProfile,
  applyProviderImportDraft,
  createProviderImportDraft,
  deleteEndpoint,
  deleteModelProfile,
  deleteRoute,
  getRegistry,
  probeRoute,
  putModelProfiles,
  putRegistryEndpoints,
  putRole,
  putRoute,
  testEndpoint,
  type ModelProfile,
  type ProviderEndpoint,
  type ProviderImportDraft,
  type ProviderRoute,
  type RoleEntry,
} from './llm'

function adapter(assertConfig: (config: InternalAxiosRequestConfig) => void): AxiosAdapter {
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

const endpoint: ProviderEndpoint = {
  endpoint_id: 'anthropic-official',
  display_name: 'Anthropic',
  protocol: 'anthropic_compatible',
  base_url: 'https://api.anthropic.example',
  api_key: 'secret',
  status: 'unverified_manual',
  timeout_seconds: 120,
  trust_env: false,
  proxy_env: null,
  metadata: {},
}

const route: ProviderRoute = {
  route_id: 'anthropic-official:claude-sonnet',
  endpoint_id: 'anthropic-official',
  route_slug: 'claude-sonnet',
  provider_model_id: 'claude-sonnet',
  canonical_id: 'claude-sonnet',
  display_name: 'Claude Sonnet',
  status: 'verified',
  capabilities: {},
  metadata: {},
}

const profile: ModelProfile = {
  model_profile_id: 'CL46T',
  display_name: 'Claude Sonnet Thinking',
  canonical_id: 'claude-sonnet',
  tags: ['thinking'],
  fallback_chain: [{ route_id: 'anthropic-official:claude-sonnet' }],
  lint_requirements: { thinking: 'error' },
}

const role: RoleEntry = {
  system_prompt_prefix: '',
  source_profile_id: null,
  source_profile_snapshot: null,
  fallback_chain: [{ route_id: 'anthropic-official:claude-sonnet' }],
  lint_requirements: { thinking: 'error' },
}

const draft: ProviderImportDraft = {
  draft_id: 'draft-1',
  source: { url: 'https://provider.example/docs' },
  status: 'pending',
  created_at: null,
  updated_at: null,
  expires_at: null,
  endpoint_candidates: {},
  route_candidates: {},
  probe_results: {},
  agent_notes: [],
  diff: {},
}

describe('llm registry api client', () => {
  afterEach(() => {
    api.defaults.adapter = undefined
  })

  it('uses registry endpoint APIs instead of legacy credentials APIs', async () => {
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
    })

    await getRegistry()
    await putRegistryEndpoints({ 'anthropic-official': endpoint })
    await testEndpoint('anthropic-official')
    await deleteEndpoint('anthropic-official')

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'get /llm/registry',
      'put /llm/registry/endpoints',
      'post /llm/endpoints/anthropic-official/test',
      'delete /llm/registry/endpoints/anthropic-official',
    ])
    expect(JSON.parse(String(seen[1].data))).toEqual({
      provider_endpoints: { 'anthropic-official': endpoint },
    })
  })

  it('uses route, role, profile, and import draft APIs', async () => {
    const seen: Array<{ method?: string; url?: string; data?: unknown; params?: unknown }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data, params: config.params })
    })

    await probeRoute('anthropic-official:claude-sonnet', { capabilities: ['thinking'] })
    await putRoute('anthropic-official:claude-sonnet', {
      display_name: route.display_name,
      canonical_id: route.canonical_id,
      status: route.status,
      capabilities: route.capabilities,
      metadata: route.metadata,
    })
    await deleteRoute('anthropic-official:claude-sonnet')
    await putRole('graph_agent', role)
    await putModelProfiles({ CL46T: profile })
    await deleteModelProfile('CL46T')
    await applyModelProfile('graph_agent', { model_profile_id: 'CL46T' })
    await createProviderImportDraft(draft)
    await applyProviderImportDraft('draft-1', 'merge')

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'post /llm/routes/anthropic-official%3Aclaude-sonnet/probe',
      'put /llm/routes/anthropic-official%3Aclaude-sonnet',
      'delete /llm/routes/anthropic-official%3Aclaude-sonnet',
      'put /llm/roles/graph_agent',
      'put /llm/model-profiles',
      'delete /llm/model-profiles/CL46T',
      'post /llm/roles/graph_agent/apply-profile',
      'post /llm/import-drafts',
      'post /llm/import-drafts/draft-1/apply',
    ])
    expect(seen.at(-1)?.params).toEqual({ mode: 'merge' })
  })
})
