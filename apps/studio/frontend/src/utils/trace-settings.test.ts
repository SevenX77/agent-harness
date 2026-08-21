import { describe, expect, it } from 'vitest'
import type { CallbackEvent } from '../api/types'
import { callSettingsDetails, settingsCarryWarning, settingsThatMoved } from './trace'

function event(settings: unknown[]): CallbackEvent {
  return {
    event_type: 'llm_call_settings',
    phase_name: 'draft',
    route_id: 'deepseek-official:deepseek-v4-pro',
    provider_model_id: 'deepseek-v4-pro',
    protocol: 'openai_compatible',
    settings,
  } as unknown as CallbackEvent
}

describe('call settings details', () => {
  it('reads every setting the gateway judged', () => {
    const details = callSettingsDetails(
      event([{ setting: 'top_p', requested: 5.0, verdict: 'adjusted', reason: 'sent as 1.0' }]),
    )

    expect(details?.settings).toEqual([
      { setting: 'top_p', requested: 5, verdict: 'adjusted', reason: 'sent as 1.0' },
    ])
    expect(details?.routeId).toBe('deepseek-official:deepseek-v4-pro')
  })

  it('drops a verdict this build has never heard of rather than rendering it as one it has', () => {
    const details = callSettingsDetails(event([{ setting: 'top_p', verdict: 'teleported' }]))

    expect(details?.settings).toEqual([])
  })

  it('says which verdicts are worth a warning', () => {
    expect(settingsCarryWarning([{ setting: 'seed', requested: 7, verdict: 'sent', reason: null }])).toBe(false)
    expect(settingsCarryWarning([{ setting: 'seed', requested: 7, verdict: 'ignored', reason: null }])).toBe(true)
  })

  // The headline says how many settings did not run as asked; the block
  // below it shows each one's own before and after. Counting is this
  // module's job, wording is the copy exit's.
  it('counts the settings that did not run as asked', () => {
    expect(settingsThatMoved([
      { setting: 'top_p', requested: 5, verdict: 'adjusted', reason: 'sent as 1.0' },
      { setting: 'seed', requested: 7, verdict: 'sent', reason: null },
    ])).toBe(1)
    expect(settingsThatMoved([
      { setting: 'seed', requested: 7, verdict: 'applied', reason: null },
    ])).toBe(0)
  })
})
