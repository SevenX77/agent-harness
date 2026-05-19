import { renderToStaticMarkup } from 'react-dom/server'
import type { ReactElement } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { CredentialsState, RoleEntry } from '../../../api/llm'
import {
  firstAvailableModel,
  getModelOptions,
  ModelPicker,
  ModelPickerMenu,
} from '../model-picker'

const role: RoleEntry = {
  temperature: 0.2,
  model_fallback: true,
  active_model: 'CL46T',
  models: {
    CL46T: { providers: ['anthropic', 'openai_proxy'] },
    DS32R: { providers: ['deepseek'] },
  },
}

const credentials: CredentialsState = {
  providers: [
    { id: 'anthropic', name: 'Anthropic', api_key: 'sk-anthropic' },
    { id: 'openai_proxy', name: 'OpenAI Proxy', api_key: '' },
    { id: 'deepseek', name: 'DeepSeek', api_key: '' },
  ],
}

type MenuButtonElement = ReactElement<{
  disabled?: boolean
  onClick?: () => void
}>

function renderMenuHtml(selectedModel = 'CL46T', nextCredentials = credentials) {
  return renderToStaticMarkup(
    <ModelPicker
      role={role}
      credentials={nextCredentials}
      selectedModel={selectedModel}
      onSelect={() => undefined}
      variant="full"
    />,
  )
}

describe('ModelPicker', () => {
  it('renders models from role', () => {
    const html = renderMenuHtml()

    expect(html).toContain('CL46T')
    expect(html).toContain('DS32R')
  })

  it('highlights the selected model', () => {
    const html = renderMenuHtml('CL46T')

    expect(html).toContain('bg-primary')
    expect(html).toContain('Select model CL46T')
  })

  it('disables a model when no provider has a key', () => {
    const options = getModelOptions(role, {
      providers: [
        { id: 'anthropic', name: 'Anthropic', api_key: '' },
        { id: 'openai_proxy', name: 'OpenAI Proxy', api_key: '' },
      ],
    })

    expect(options.find((option) => option.modelCode === 'CL46T')?.available).toBe(false)
  })

  it('enables a model when any provider has a key', () => {
    const options = getModelOptions(role, credentials)

    expect(options.find((option) => option.modelCode === 'CL46T')?.available).toBe(true)
  })

  it('calls onSelect when an available model is selected', () => {
    const onSelect = vi.fn()
    const options = getModelOptions(role, credentials)
    const element = ModelPickerMenu({ options, selectedModel: 'DS32R', onSelect })
    const buttons: MenuButtonElement[] = Array.isArray(element.props.children)
      ? element.props.children
      : [element.props.children]
    const cl46t = buttons.find((button) => button.key === 'CL46T')

    cl46t?.props.onClick?.()

    expect(onSelect).toHaveBeenCalledWith('CL46T')
  })

  it('does not attach a click handler to disabled models', () => {
    const onSelect = vi.fn()
    const options = getModelOptions(role, credentials)
    const element = ModelPickerMenu({ options, selectedModel: 'CL46T', onSelect })
    const buttons: MenuButtonElement[] = Array.isArray(element.props.children)
      ? element.props.children
      : [element.props.children]
    const ds32r = buttons.find((button) => button.key === 'DS32R')

    expect(ds32r?.props.disabled).toBe(true)
    expect(ds32r?.props.onClick).toBeUndefined()
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('renders the icon variant trigger', () => {
    const html = renderToStaticMarkup(
      <ModelPicker
        role={role}
        credentials={credentials}
        selectedModel="CL46T"
        onSelect={() => undefined}
      />,
    )

    expect(html).toContain('Select Copilot model')
    expect(html).toContain('aria-expanded="false"')
  })

  it('renders the full variant as a button group', () => {
    const html = renderMenuHtml()

    expect(html).toContain('Copilot model picker')
    expect(html).toContain('Select model CL46T')
  })

  it('shows a disabled placeholder without role data', () => {
    const html = renderToStaticMarkup(
      <ModelPicker
        role={null}
        credentials={credentials}
        selectedModel=""
        onSelect={() => undefined}
      />,
    )

    expect(html).toContain('disabled=""')
    expect(html).toContain('Copilot model config unavailable')
  })

  it('returns the first available model', () => {
    const options = getModelOptions(role, credentials)

    expect(firstAvailableModel(options)).toBe('CL46T')
  })
})
