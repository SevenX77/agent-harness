import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { TooltipProvider } from '@/components/ui/tooltip'
import { CenterActionBar, type SkillBuildStage } from './center-action-bar'

const PREDICT_LOCK_REASON = 'Compile must pass first'
const RUN_LOCK_REASON = 'Predict must pass first'
const BACKEND_UNAVAILABLE_REASON = 'Backend unavailable — reconnecting'

function renderBar(stage: SkillBuildStage, backendReachable?: boolean): string {
  return renderToStaticMarkup(
    <TooltipProvider>
      <CenterActionBar stage={stage} backendReachable={backendReachable} />
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
    for (const stage of ['predict-pass', 'running', 'paused'] as const) {
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

  it('shows no lock reasons at all once both gates are open', () => {
    const html = renderBar('predict-pass')
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

  it('holds the canvas centre and only gives way to an overlay that would cover it', () => {
    // Two reports, one rule. Centring on the window slid the bar under the copilot
    // panel; recentring on the gap between the overlays made it jump sideways on
    // every panel toggle. It therefore stays at the host centre and is clamped
    // only by an overlay it would actually collide with.
    const html = renderBar('idle')

    expect(html).toContain('data-studio-center-action-bar="true"')
    expect(html).toContain('-translate-x-1/2')
    expect(html).toContain('clamp(')
    expect(html).toContain('50%')
    expect(html).toContain('--studio-canvas-left-safe-area')
    expect(html).toContain('--studio-canvas-right-safe-area')
    expect(html).toContain('--studio-action-bar-width')
    expect(html).not.toContain('left-1/2')
  })

  it('offers both futures of a run in flight: pause it or end it', () => {
    // A disabled Run button says "wait" without saying how to not wait. A run in
    // flight has the same two futures a paused one has, and the backend already
    // takes either in one step (`test_stopping_a_run_in_flight_skips_the_pause`).
    // Offering only Pause made "I want this to stop" a two-click detour through
    // a state the reader did not ask for.
    const running = renderBar('running')

    expect(running).toContain('Pause')
    expect(running).toContain('Stop')
    expect(running).not.toContain('Resume')
  })

  it('offers both futures of a paused run: resume it or end it', () => {
    const paused = renderBar('paused')

    expect(paused).toContain('Resume')
    expect(paused).toContain('Stop')
    expect(paused).not.toContain('Pause')
  })

  it('goes back to Run once nothing is in flight', () => {
    const idle = renderBar('predict-pass')

    expect(idle).toContain('Run')
    expect(idle).not.toContain('Pause')
    expect(idle).not.toContain('Stop')
  })

  it('offers a live Run in exactly the one stage that can start a run', () => {
    // `Workspace.handleRun` starts a run only from `predict-pass` and returns in
    // silence otherwise. Any other stage that renders an ENABLED Run is therefore
    // a dead control — the button invites a click and nothing happens, with no
    // toast and no log. Pinning both halves of that rule here keeps them from
    // drifting apart again.
    // Typed as a total record so adding a stage to the union makes this fail to
    // compile until the new stage is classified here too.
    const everyStage: Record<SkillBuildStage, true> = {
      idle: true,
      compiling: true,
      'compile-fail': true,
      'compile-pass': true,
      predicting: true,
      'predict-fail': true,
      'predict-pass': true,
      running: true,
      paused: true,
    }

    const liveRun = (Object.keys(everyStage) as SkillBuildStage[]).filter((stage) => {
      const html = renderBar(stage)
      return html.includes('Run') && !html.includes('disabled=""')
    })

    expect(liveRun).toEqual(['predict-pass'])
  })
})

// dead-sidecar-says-so (2026-08-24): "功能面带原因置灰,不是无声的灰按钮" — the
// sidecar-dependent action buttons must disable AND say why once RuntimeGate
// detects the backend is down, using the same lock-reason affordance already
// established for the compile/predict/run gating above (#13).
describe('CenterActionBar — disabled with a reason when the backend is unreachable', () => {
  it('disables Compile with the backend-unavailable reason even in a normally-enabled stage', () => {
    const html = renderBar('idle', false)

    expect(html).toContain(`aria-label="${BACKEND_UNAVAILABLE_REASON}"`)
  })

  it('disables Predict with the backend-unavailable reason, overriding its usual reason once compile has passed', () => {
    const html = renderBar('compile-pass', false)

    expect(html).toContain(`aria-label="${BACKEND_UNAVAILABLE_REASON}"`)
    expect(html).not.toContain(`aria-label="${PREDICT_LOCK_REASON}"`)
  })

  it('disables Run with the backend-unavailable reason, overriding its usual reason once predict has passed', () => {
    const html = renderBar('predict-pass', false)

    expect(html).toContain(`aria-label="${BACKEND_UNAVAILABLE_REASON}"`)
    expect(html).not.toContain(`aria-label="${RUN_LOCK_REASON}"`)
  })

  it('leaves the normal stage-driven gating untouched when the backend IS reachable', () => {
    const reachableTrue = renderBar('idle', true)
    const reachableOmitted = renderBar('idle')

    expect(reachableTrue).not.toContain(BACKEND_UNAVAILABLE_REASON)
    expect(reachableOmitted).not.toContain(BACKEND_UNAVAILABLE_REASON)
  })

  it('every button in the bar is disabled while the backend is unreachable, in every stage', () => {
    const everyStage: SkillBuildStage[] = [
      'idle',
      'compiling',
      'compile-fail',
      'compile-pass',
      'predicting',
      'predict-fail',
      'predict-pass',
      'running',
      'paused',
    ]

    for (const stage of everyStage) {
      const html = renderBar(stage, false)
      const disabledCount = (html.match(/disabled=""/g) ?? []).length
      const buttonCount = (html.match(/<button/g) ?? []).length
      expect(disabledCount, `stage=${stage}: expected every button disabled`).toBe(buttonCount)
    }
  })
})
