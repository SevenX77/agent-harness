import { afterEach, describe, expect, it } from 'vitest'
import i18n from '@/i18n'
import { GraphEditError, type GraphEditProblem } from './canvas-authoring'
import { graphEditErrorMessage, graphEditProblemMessage } from './graph-edit-problem-message'

const EVERY_PROBLEM_CODE: readonly GraphEditProblem['code'][] = [
  'connect_endpoints_must_be_phases',
  'self_dependency',
  'input_target_must_be_phase',
  'dependency_exists',
  'output_source_must_be_phase',
  'output_marker_exists',
  'connect_boundary_direction',
  'disconnect_endpoints_must_be_phases',
  'input_source_must_be_phase',
  'input_dependency_missing',
  'output_disconnect_source_must_be_phase',
  'output_marker_missing',
  'disconnect_boundary_direction',
  'phase_dependency_missing',
  'phase_id_required',
  'phase_not_found',
  'select_phase_to_rename',
  'name_unchanged',
  'phase_not_in_graph',
  'reconnect_endpoints_must_be_phases',
  'reconnect_no_op',
  'name_required',
  'name_shape_invalid',
  'name_taken',
]

afterEach(async () => {
  await i18n.changeLanguage('en')
})

describe('graphEditProblemMessage', () => {
  it('renders the same refusal in whichever language the reader chose', async () => {
    const problem: GraphEditProblem = { code: 'self_dependency' }

    await i18n.changeLanguage('en')
    expect(graphEditProblemMessage(problem)).toBe('A phase cannot depend on itself.')

    await i18n.changeLanguage('zh-CN')
    expect(graphEditProblemMessage(problem)).toBe('一个相位不能依赖它自己。')
  })

  it('puts the offending phase name into the sentence in both languages', async () => {
    const problem: GraphEditProblem = { code: 'name_taken', phaseId: 'draft' }

    await i18n.changeLanguage('en')
    expect(graphEditProblemMessage(problem)).toBe('A phase named draft already exists.')

    await i18n.changeLanguage('zh-CN')
    expect(graphEditProblemMessage(problem)).toBe('已经有一个叫 draft 的相位了。')
  })

  it('has copy for every code the validators can produce, in every language', async () => {
    for (const language of ['en', 'zh-CN']) {
      await i18n.changeLanguage(language)
      for (const code of EVERY_PROBLEM_CODE) {
        const problem = (code === 'name_taken'
          ? { code, phaseId: 'draft' }
          : { code }) as GraphEditProblem
        const message = graphEditProblemMessage(problem)
        expect(message, `${code} in ${language}`).not.toBe(`problem.${code}`)
        expect(message, `${code} in ${language}`).not.toBe('')
      }
    }
  })
})

describe('graphEditErrorMessage', () => {
  it('translates a refusal the canvas raised', async () => {
    await i18n.changeLanguage('zh-CN')
    const error = new GraphEditError({ code: 'dependency_exists' })
    expect(graphEditErrorMessage(error, 'fallback')).toBe('这条依赖已经存在。')
  })

  it('passes through a failure that already carries its own sentence', () => {
    const error = new Error('cannot finalize write: locked')
    expect(graphEditErrorMessage(error, 'fallback')).toBe('cannot finalize write: locked')
  })

  it('falls back when the rejection says nothing', () => {
    expect(graphEditErrorMessage('boom', 'Could not delete node')).toBe('Could not delete node')
  })
})
