import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
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
    onSetActiveBackend: vi.fn(),
    onTestBackend: vi.fn(),
    onSaveBackend: vi.fn(),
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
    active: true,
    status: credentials.backends.claude,
    draft: { apiKey: '', baseUrl: '', advancedOpen: false },
    testState: { status: 'idle' },
    onDraftChange: vi.fn(),
    onTest: vi.fn(),
    onSave: vi.fn(),
    ...overrides,
  }
  return { props, element: BackendCredentialCard(props) }
}

describe('SettingsPage', () => {
  it('renders the three main tabs and general settings', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)

    expect(html).toContain('General')
    expect(html).toContain('AI &amp; Copilot')
    expect(html).toContain('Advanced')
    expect(html).toContain('Studio User ID')
    expect(html).toContain('Gitea Host')
  })

  it('renders four backend cards and masks configured keys', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps({ activeTab: 'copilot' })} />)

    expect(html).toContain('Claude')
    expect(html).toContain('OpenAI')
    expect(html).toContain('DeepSeek')
    expect(html).toContain('Gemini')
    expect(html).toContain('••••abcd')
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

  it('surfaces Save for dirty API key drafts', () => {
    const onSave = vi.fn()
    const draft: BackendDraft = { apiKey: 'sk-new', baseUrl: '', advancedOpen: false }
    const { element } = cardElement({ draft, onSave })
    const button = findByAriaLabel(element, 'Save Claude credentials')

    ;(button?.props.onClick as (() => void) | undefined)?.()

    expect(onSave).toHaveBeenCalledOnce()
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
