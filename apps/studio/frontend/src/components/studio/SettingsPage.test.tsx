import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  DEFAULT_CREDENTIALS,
  ProviderCard,
  SettingsPageContent,
  appendProvider,
  buildCredentialsFromDrafts,
  createDebouncedSaver,
  customProvider,
  draftsFromCredentials,
  removeProvider,
} from './SettingsPage'
import type { ProviderConfig, TestProviderResponse } from '../../api/copilot'

function baseViewProps(overrides: Partial<Parameters<typeof SettingsPageContent>[0]> = {}): Parameters<typeof SettingsPageContent>[0] {
  return {
    credentials: DEFAULT_CREDENTIALS,
    drafts: draftsFromCredentials(DEFAULT_CREDENTIALS),
    expandedIds: new Set(),
    visibleKeyIds: new Set(),
    testingIds: new Set(),
    testResults: {},
    addDialogOpen: false,
    newProvider: { name: '', kind: 'openai-compat' },
    onClose: vi.fn(),
    onActiveProviderChange: vi.fn(),
    onDraftChange: vi.fn(),
    onToggleExpanded: vi.fn(),
    onToggleKeyVisible: vi.fn(),
    onTestProvider: vi.fn(),
    onDeleteProvider: vi.fn(),
    onAddDialogOpenChange: vi.fn(),
    onNewProviderChange: vi.fn(),
    onConfirmAddProvider: vi.fn(),
    ...overrides,
  }
}

function findByAriaLabel(node: ReactNode, label: string): ReactElement<Record<string, unknown>> | null {
  if (!isValidElement(node)) return null
  const element = node as ReactElement<Record<string, unknown> & { children?: ReactNode }>
  if (element.props['aria-label'] === label) return element
  const children = element.props.children
  if (Array.isArray(children)) {
    for (const child of children) {
      const match = findByAriaLabel(child, label)
      if (match) return match
    }
  }
  return findByAriaLabel(children, label)
}

function findWithProp(node: ReactNode, prop: string): ReactElement<Record<string, unknown>> | null {
  if (!isValidElement(node)) return null
  const element = node as ReactElement<Record<string, unknown> & { children?: ReactNode }>
  if (prop in element.props) return element
  const children = element.props.children
  if (Array.isArray(children)) {
    for (const child of children) {
      const match = findWithProp(child, prop)
      if (match) return match
    }
  }
  return findWithProp(children, prop)
}

function cardElement(overrides: Partial<Parameters<typeof ProviderCard>[0]> = {}) {
  const provider = DEFAULT_CREDENTIALS.providers[0]
  const props: Parameters<typeof ProviderCard>[0] = {
    provider,
    draft: { ...provider, api_key: 'sk-plaintext' },
    active: true,
    expanded: true,
    keyVisible: false,
    testing: false,
    testResult: null,
    onDraftChange: vi.fn(),
    onToggleExpanded: vi.fn(),
    onToggleKeyVisible: vi.fn(),
    onTest: vi.fn(),
    onDelete: vi.fn(),
    ...overrides,
  }
  return { props, element: ProviderCard(props) }
}

describe('SettingsPage v2', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders four default provider cards', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)

    expect(html).toContain('AI &amp; Copilot')
    expect(html).toContain('Claude')
    expect(html).toContain('OpenAI')
    expect(html).toContain('DeepSeek')
    expect(html).toContain('Gemini')
    expect(html).toContain('Add Custom Provider')
  })

  it('updates draft API keys and exposes the eye toggle', () => {
    const onDraftChange = vi.fn()
    const onToggleKeyVisible = vi.fn()
    const { element } = cardElement({ onDraftChange, onToggleKeyVisible })
    const input = findByAriaLabel(element, 'Claude API key')
    const eye = findByAriaLabel(element, 'Show Claude API key')

    ;(input?.props.onChange as ((event: { target: { value: string } }) => void) | undefined)?.({
      target: { value: 'sk-new' },
    })
    ;(eye?.props.onClick as (() => void) | undefined)?.()

    expect(onDraftChange).toHaveBeenCalledWith({ api_key: 'sk-new' })
    expect(onToggleKeyVisible).toHaveBeenCalledOnce()
  })

  it('debounces PUT saves for 650ms', async () => {
    vi.useFakeTimers()
    const save = vi.fn<() => Promise<void>>().mockResolvedValue(undefined)
    const saver = createDebouncedSaver(save, 650)

    saver.schedule(DEFAULT_CREDENTIALS)
    await vi.advanceTimersByTimeAsync(649)
    expect(save).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)

    expect(save).toHaveBeenCalledWith(DEFAULT_CREDENTIALS)
  })

  it('renders models and thinking chips after test', () => {
    const result: TestProviderResponse = {
      status: 'ok',
      latency_ms: 234,
      models: [
        { id: 'claude-opus-4-7', supports_thinking: true, supports_vision: true },
        { id: 'claude-haiku-4-5', supports_thinking: false, supports_vision: true },
      ],
      message: null,
    }

    const html = renderToStaticMarkup(<ProviderCard {...cardElement({ testResult: result }).props} />)

    expect(html).toContain('Connected')
    expect(html).toContain('latency_ms=234')
    expect(html).toContain('Available Models (2)')
    expect(html).toContain('claude-opus-4-7')
    expect(html).toContain('🧠')
  })

  it('adds custom providers and deletes custom providers with active fallback', () => {
    const custom = customProvider('Ollama Local', 'openai-compat')
    const added = appendProvider(DEFAULT_CREDENTIALS, custom)
    const activeCustom = { ...added, active_provider_id: custom.id }
    const removed = removeProvider(activeCustom, custom.id)

    expect(added.providers.some((provider) => provider.id === custom.id)).toBe(true)
    expect(custom.id).toMatch(/^custom-[a-z0-9]{8}$/)
    expect(removed.providers.some((provider) => provider.id === custom.id)).toBe(false)
    expect(removed.active_provider_id).toBe('default-claude')
  })

  it('changes the default model from discovered model options', () => {
    const onDraftChange = vi.fn()
    const result: TestProviderResponse = {
      status: 'ok',
      models: [{ id: 'claude-sonnet-4-5', supports_thinking: true, supports_vision: true }],
    }
    const { element } = cardElement({ onDraftChange, testResult: result })
    const select = findWithProp(element, 'onValueChange')

    ;(select?.props.onValueChange as ((value: string) => void) | undefined)?.('claude-sonnet-4-5')

    expect(onDraftChange).toHaveBeenCalledWith({ active_model_id: 'claude-sonnet-4-5' })
  })

  it('builds PUT payloads from drafts without masking plaintext keys', () => {
    const drafts = draftsFromCredentials(DEFAULT_CREDENTIALS)
    const claude: ProviderConfig = { ...drafts['default-claude'], api_key: 'sk-plaintext' }
    const next = buildCredentialsFromDrafts(DEFAULT_CREDENTIALS, {
      ...drafts,
      'default-claude': claude,
    })

    expect(next.providers[0].api_key).toBe('sk-plaintext')
  })
})
