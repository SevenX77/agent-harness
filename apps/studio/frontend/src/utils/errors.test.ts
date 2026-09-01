import { afterEach, describe, expect, it } from 'vitest'
import { AxiosError, AxiosHeaders, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import i18n from '../i18n'
import { errorDiagnosticDetails, errorMessage } from './errors'

function backendError(payload: Record<string, unknown>): AxiosError {
  const config: InternalAxiosRequestConfig = {
    baseURL: 'http://127.0.0.1:8787/api',
    url: '/skills/demo/publish',
    method: 'post',
    headers: new AxiosHeaders(),
  }
  const response: AxiosResponse = {
    config,
    data: payload,
    headers: {},
    status: 400,
    statusText: 'Bad Request',
  }
  return new AxiosError('Request failed with status code 400', 'ERR_BAD_REQUEST', config, {}, response)
}

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

// Which language a typed failure is read in is a fact about the reader, so the
// frontend decides it. The server used to: `skills.py` wrote these two messages
// in Chinese and they went into the toast verbatim (ledger K4).
describe('errorMessage for a typed backend failure', () => {
  afterEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('renders the code in the reader language, with details filling the blanks', async () => {
    const error = backendError({
      error_code: 'APP_SETTINGS_INCOMPLETE',
      http_status: 400,
      message: 'app settings incomplete: gitea_host is not set',
      details: { field: 'gitea_host' },
    })

    await i18n.changeLanguage('en')
    expect(errorMessage(error)).toBe('Settings are incomplete: gitea_host is not set. Open Settings to set it.')

    await i18n.changeLanguage('zh-CN')
    expect(errorMessage(error)).toContain('gitea_host')
    expect(errorMessage(error)).not.toBe('app settings incomplete: gitea_host is not set')
  })

  it('falls back to the backend message for a code nobody has written a reader-facing text for', () => {
    expect(errorMessage(backendError({
      error_code: 'PUBLISH_FAILED',
      http_status: 400,
      message: 'remote rejected: non-fast-forward',
    }))).toBe('remote rejected: non-fast-forward')
  })

  // Studio codes and LLM-provider codes live in SEPARATE key spaces
  // (`studioCodes.*` here, `providerCodes.*` in `lib/llm-error-messages.ts`)
  // because only one of the two is ours to name: the gateway's
  // `vendor_error_code` hands back the remote provider's own `code`/`type`/
  // `status` string verbatim (`probing/judge.py:338`), so that space is
  // open-ended and outside our control. While both readers shared one
  // `codes.*` table, a Studio `error_code` that happened to spell a provider
  // code got answered with the PROVIDER's sentence — the reader was told the
  // wrong machine had failed.
  it('never answers a Studio error_code with a provider sentence', () => {
    expect(errorMessage(backendError({
      error_code: 'invalid_api_key',
      http_status: 500,
      message: 'studio could not read the stored credential file',
    }))).toBe('studio could not read the stored credential file')
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
