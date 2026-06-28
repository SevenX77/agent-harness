import { describe, expect, it } from 'vitest'
import { errorMessage } from './errors'

describe('errorMessage', () => {
  it('surfaces nested Tauri command messages', () => {
    expect(errorMessage({
      type: 'WriteFailed',
      data: { message: 'cannot finalize write: locked' },
    })).toBe('cannot finalize write: locked')
  })

  it('summarizes native optimistic-lock conflicts without dumping the file body', () => {
    expect(errorMessage({
      type: 'HashConflict',
      data: {
        current_hash: 'new-hash',
        current_content: 'large file body',
      },
    })).toBe('File changed on disk. Reload the file and try again.')
  })
})
