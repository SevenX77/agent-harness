import { describe, expect, it } from 'vitest'
import { AxiosError, AxiosHeaders, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { errorDiagnosticDetails, errorMessage } from './errors'

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

describe('errorDiagnosticDetails', () => {
  it('includes structured backend error response details for drawer display', () => {
    const config: InternalAxiosRequestConfig = {
      baseURL: 'http://127.0.0.1:8787/api',
      url: '/skills/text-segmentation/runs/predict',
      method: 'post',
      headers: new AxiosHeaders(),
    }
    const response: AxiosResponse = {
      config,
      data: {
        error_code: 'PREDICT_FAILED',
        http_status: 422,
        message: 'List schema shorthand must contain exactly one item type',
        details: {
          engine_error_code: 'engine.schema_invalid',
          run_id: 'predict-error-1',
        },
        retry_strategy: 'not_retryable',
      },
      headers: {},
      status: 422,
      statusText: 'Unprocessable Entity',
    }

    const details = errorDiagnosticDetails(
      new AxiosError('Request failed with status code 422', 'ERR_BAD_RESPONSE', config, {}, response),
    )

    expect(details).toContain('Backend error code: PREDICT_FAILED')
    expect(details).toContain('Retry strategy: not_retryable')
    expect(details.join('\n')).toContain('"engine_error_code": "engine.schema_invalid"')
    expect(details.join('\n')).toContain('"run_id": "predict-error-1"')
  })
})
