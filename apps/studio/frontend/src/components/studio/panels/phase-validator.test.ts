import { describe, expect, it } from 'vitest'
import { validatorFilePath, validatorStubContent } from './phase-validator'

describe('validator file helpers', () => {
  it('builds the sibling validator.py path for a phase', () => {
    expect(validatorFilePath('segment')).toBe('phases/segment/validator.py')
  })

  it('stub exports a validate() matching the engine signature and passes by default', () => {
    const stub = validatorStubContent()
    // VALIDATOR_SIGNATURE: def validate(output: dict, state_slice: dict, **kwargs) -> None | dict
    expect(stub).toContain('def validate(')
    expect(stub).toContain('output')
    expect(stub).toContain('state_slice')
    // Returning None means "no errors" — a freshly created validator must not reject.
    expect(stub).toContain('return None')
  })
})
