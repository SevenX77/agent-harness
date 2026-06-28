import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { TooltipProvider } from '@/components/ui/tooltip'
import { CenterActionBar, type SkillBuildStage } from './center-action-bar'

const PREDICT_LOCK_REASON = 'Compile must pass first'
const RUN_LOCK_REASON = 'Predict must pass first'

function renderBar(stage: SkillBuildStage): string {
  return renderToStaticMarkup(
    <TooltipProvider>
      <CenterActionBar stage={stage} />
    </TooltipProvider>,
  )
}

describe('CenterActionBar lock-reason hint (#13)', () => {
  it('shows "Compile must pass first" on the locked Predict button before compile passes', () => {
    for (const stage of ['idle', 'compiling', 'compile-fail'] as const) {
      const html = renderBar(stage)
      // The locked Predict button exposes the gate reason for hover + a11y discovery.
      expect(html).toContain(`aria-label="${PREDICT_LOCK_REASON}"`)
    }
  })

  it('shows "Predict must pass first" on the locked Run button before predict passes', () => {
    for (const stage of [
      'idle',
      'compile-fail',
      'compile-pass',
      'predicting',
      'predict-fail',
    ] as const) {
      const html = renderBar(stage)
      expect(html).toContain(`aria-label="${RUN_LOCK_REASON}"`)
    }
  })

  it('does not show the Run lock reason once predict has passed and Run is unlocked', () => {
    for (const stage of ['predict-pass', 'running', 'run-fail'] as const) {
      const html = renderBar(stage)
      expect(html).not.toContain(`aria-label="${RUN_LOCK_REASON}"`)
    }
  })

  it('does not show the Predict lock reason once compile has passed and Predict is unlocked', () => {
    for (const stage of ['compile-pass', 'predicting', 'predict-fail', 'predict-pass'] as const) {
      const html = renderBar(stage)
      expect(html).not.toContain(`aria-label="${PREDICT_LOCK_REASON}"`)
    }
  })

  it('shows no lock reasons at all when every gate is open (run-fail unlocks all)', () => {
    const html = renderBar('run-fail')
    expect(html).not.toContain(PREDICT_LOCK_REASON)
    expect(html).not.toContain(RUN_LOCK_REASON)
  })
})

describe('CenterActionBar canvas surface styling', () => {
  it('uses the shared canvas action surface instead of a plain card bar', () => {
    const html = renderBar('idle')

    expect(html).toContain('studio-center-action-bar')
    expect(html).toContain('studio-center-action-button')
    expect(html).toContain('studio-center-action-button--active')
  })

  it('is fixed to the viewport center and exposes a stable measurement hook', () => {
    const html = renderBar('idle')

    expect(html).toContain('data-studio-center-action-bar="true"')
    expect(html).toContain('fixed')
    expect(html).toContain('left-1/2')
    expect(html).toContain('-translate-x-1/2')
  })
})

describe('CenterActionBar corner-radius convergence (FRONTEND_UI_SPEC §2.4)', () => {
  it('uses rounded-md and never rounded-full on the shell and all three buttons', () => {
    const html = renderBar('idle')
    expect(html).not.toContain('rounded-full')
    // Shell container + Compile + Predict + Run all carry rounded-md.
    const roundedMdCount = (html.match(/rounded-md/g) ?? []).length
    expect(roundedMdCount).toBeGreaterThanOrEqual(4)
  })

  it('keeps rounded-md across every stage', () => {
    for (const stage of [
      'idle',
      'compiling',
      'compile-fail',
      'compile-pass',
      'predicting',
      'predict-fail',
      'predict-pass',
      'running',
      'run-fail',
    ] as const) {
      const html = renderBar(stage)
      expect(html).not.toContain('rounded-full')
      expect(html).toContain('rounded-md')
    }
  })
})
