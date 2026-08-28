// @vitest-environment jsdom
/**
 * Starting a skill by talking it through, instead of being handed a template.
 *
 * New Skill made a folder of starter files and dropped you on a canvas of them
 * — an answer for someone who already knows the shape they want, and nothing at
 * all for someone who has an idea. F6 says the wizard is the OTHER way in,
 * offered beside the default rather than replacing it (D-1-4: the plain
 * template path stays exactly as it was).
 *
 * Design: copilot-assist/mvp1-alignment.md F6.
 */

import { act, type ComponentProps } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { NewSkillDialog } from './NewSkillDialog'
import { buildSkillWizardDraft } from '../copilot/skill-wizard-draft'

describe('the New Skill dialog offers both ways in', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    document.body.innerHTML = ''
  })

  type DialogProps = ComponentProps<typeof NewSkillDialog>

  function render(overrides: Partial<DialogProps> = {}) {
    const props: DialogProps = {
      open: true,
      onOpenChange: vi.fn(),
      newSkillName: 'invoice-reader',
      onNewSkillNameChange: vi.fn(),
      parentDirectory: 'D:\\skills',
      defaultParentDirectory: 'D:\\skills',
      selectingParentDirectory: false,
      onChooseParentDirectory: vi.fn(),
      newSkillError: null,
      creating: false,
      onSubmit: vi.fn(),
      onSubmitWithWizard: vi.fn(),
      ...overrides,
    }
    act(() => {
      root.render(<NewSkillDialog {...props} />)
    })
    return props
  }

  function buttonNamed(pattern: RegExp): HTMLButtonElement | undefined {
    return [...document.querySelectorAll('button')].find((button) =>
      pattern.test(button.textContent ?? ''),
    ) as HTMLButtonElement | undefined
  }

  it('keeps the plain template action', () => {
    render()

    expect(buttonNamed(/^Create$/)).toBeTruthy()
  })

  it('offers to plan the skill together instead', () => {
    render()

    expect(buttonNamed(/Plan it together/)).toBeTruthy()
  })

  it('asks for the wizard only through its own action', () => {
    const props = render()

    act(() => {
      buttonNamed(/Plan it together/)?.click()
    })

    expect(props.onSubmitWithWizard).toHaveBeenCalledTimes(1)
    expect(props.onSubmit).not.toHaveBeenCalled()
  })

  it('needs a name before either way in', () => {
    render({ newSkillName: '   ' })

    expect(buttonNamed(/^Create$/)?.disabled).toBe(true)
    expect(buttonNamed(/Plan it together/)?.disabled).toBe(true)
  })
})

describe('what the wizard opens with', () => {
  it('names the skill it is about but no agent-skill asset — routing is by description (用户裁决 2026-08-27)', () => {
    // A real new user does not know which agent skills exist; the canned
    // opener must read like their own ask, and the agent picks the wizard
    // asset by its description — naming it here would mask routing failures.
    const draft = buildSkillWizardDraft({ skillId: 'invoice-reader' })

    expect(draft).toContain('invoice-reader')
    expect(draft).not.toContain('brainstorming')
  })

  it('asks for one question at a time rather than a questionnaire', () => {
    const draft = buildSkillWizardDraft({ skillId: 'invoice-reader' })

    expect(draft).toMatch(/一次问一个|one question/)
  })
})
