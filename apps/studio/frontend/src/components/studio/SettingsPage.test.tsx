import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  BACKENDS,
  BackendCredentialCard,
  SettingsPageContent,
  draftsFromCredentials,
  type BackendDraft,
} from './SettingsPage'
import type { CopilotCredentials } from '../../types/copilot'

const credentials: CopilotCredentials = {
  active_backend: 'claude',
  backends: {
    claude: { has_key: true, last4: 'abcd', base_url: '' },
    openai: { has_key: false, last4: null, base_url: '' },
    deepseek: { has_key: false, last4: null, base_url: 'https://deepseek.example' },
    gemini: { has_key: false, last4: null, base_url: '' },
  },
}

function baseViewProps(overrides: Partial<Parameters<typeof SettingsPageContent>[0]> = {}): Parameters<typeof SettingsPageContent>[0] {
  return {
    activeTab: 'general',
    credentials,
    drafts: draftsFromCredentials(credentials),
    testStates: {
      claude: { status: 'idle' },
      openai: { status: 'idle' },
      deepseek: { status: 'idle' },
      gemini: { status: 'idle' },
    },
    appSettings: {
      userId: 'alice',
      giteaHost: 'https://gitea.example.com',
      isLoading: false,
      setUserId: vi.fn(),
      setGiteaHost: vi.fn(),
      save: vi.fn(),
    },
    onClose: vi.fn(),
    onTabChange: vi.fn(),
    onDraftChange: vi.fn(),
    onToggleKeyVisible: vi.fn(),
    visibleKeys: {},
    onTestBackend: vi.fn(),
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

function cardElement(overrides: Partial<Parameters<typeof BackendCredentialCard>[0]> = {}) {
  const backend = BACKENDS[0]
  const props: Parameters<typeof BackendCredentialCard>[0] = {
    backend,
    status: credentials.backends.claude,
    draft: { apiKey: '', baseUrl: '', advancedOpen: false },
    testState: { status: 'idle' },
    keyVisible: false,
    onDraftChange: vi.fn(),
    onToggleKeyVisible: vi.fn(),
    onTest: vi.fn(),
    ...overrides,
  }
  return { props, element: BackendCredentialCard(props) }
}

describe('SettingsPage', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders the three main tabs and general settings', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)

    expect(html).toContain('General')
    expect(html).toContain('AI &amp; Copilot')
    expect(html).toContain('Advanced')
    expect(html).toContain('Studio User ID')
    expect(html).toContain('Gitea Host')
  })

  it('renders four backend cards without active backend controls or key masks', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps({ activeTab: 'copilot' })} />)

    expect(html).toContain('Claude')
    expect(html).toContain('OpenAI')
    expect(html).toContain('DeepSeek')
    expect(html).toContain('Gemini')
    expect(html).not.toContain('Active Backend')
    expect(html).not.toContain('••••abcd')
    expect(html).not.toContain('Active</span>')
  })

  it('invokes the test handler from backend cards', () => {
    const onTest = vi.fn()
    const { element } = cardElement({ onTest })
    const button = findByAriaLabel(element, 'Test Claude credentials')

    ;(button?.props.onClick as (() => void) | undefined)?.()

    expect(onTest).toHaveBeenCalledOnce()
  })

  it('renders successful and invalid key test states', () => {
    const okHtml = renderToStaticMarkup(
      <BackendCredentialCard
        {...cardElement().props}
        testState={{ status: 'ok', result: { status: 'ok', latency_ms: 42, model_seen: 'claude-sonnet' } }}
      />,
    )
    const errorHtml = renderToStaticMarkup(
      <BackendCredentialCard
        {...cardElement().props}
        testState={{ status: 'error', result: { status: 'invalid_key', message: 'Provider rejected key' } }}
      />,
    )

    expect(okHtml).toContain('OK')
    expect(okHtml).toContain('claude-sonnet')
    expect(errorHtml).toContain('Invalid API key')
  })

  it('renders plaintext local draft behind a password field with an eye toggle', () => {
    const draft: BackendDraft = { apiKey: 'sk-new', baseUrl: '', advancedOpen: false }
    const { element } = cardElement({ draft })
    const input = findByAriaLabel(element, 'Claude API key')
    const button = findByAriaLabel(element, 'Show Claude API key')

    expect(input?.props.value).toBe('sk-new')
    expect(input?.props.type).toBe('password')
    expect(input?.props.autoComplete).toBe('new-password')
    expect(input?.props.name).toBeUndefined()
    expect(button).not.toBeNull()
  })

  it('passes changed API keys through draft updates', () => {
    const onDraftChange = vi.fn()
    const { element } = cardElement({ onDraftChange })
    const input = findByAriaLabel(element, 'Claude API key')

    ;(input?.props.onChange as ((event: { target: { value: string } }) => void) | undefined)?.({
      target: { value: 'sk-new' },
    })

    expect(onDraftChange).toHaveBeenCalledWith({ apiKey: 'sk-new' })
  })
})
