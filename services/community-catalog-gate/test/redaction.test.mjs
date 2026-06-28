// Gate server-side re-validation tests (defense in depth). These mirror the
// desktop client's redaction red-lines: the gate independently rejects any record
// that carries a forbidden field, the wrong type/trust state, a non-allowlisted
// (private) base URL, or a bare fingerprint without its plaintext URL.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  PUBLIC_PROVIDER_HOST_ALLOWLIST,
  UPLOADABLE_TRUST_STATE,
  WIRE_EVIDENCE_TYPE,
  screenBatch,
  validateUploadRecord,
} from '../src/redaction.mjs';

function record(overrides = {}) {
  return {
    evidence_type: WIRE_EVIDENCE_TYPE,
    trust_state: UPLOADABLE_TRUST_STATE,
    provider_model_id: 'gpt-4o',
    model_id: 'gpt-4o',
    method_id: 'chat.completions',
    capability_family: 'text',
    normalized_public_base_url: 'https://api.openai.com/v1',
    endpoint_fingerprint: 'fp',
    ...overrides,
  };
}

test('accepts a well-formed allowlisted record', () => {
  assert.deepEqual(validateUploadRecord(record()), { ok: true });
});

test('rejects a forbidden/extra field (no secrets by construction)', () => {
  const verdict = validateUploadRecord(record({ api_key: 'sk-LEAK' }));
  assert.equal(verdict.ok, false);
  assert.match(verdict.reason, /^forbidden_field:/);
});

test('rejects the wrong wire evidence_type', () => {
  assert.deepEqual(validateUploadRecord(record({ evidence_type: 'probe' })), {
    ok: false,
    reason: 'wrong_evidence_type',
  });
});

test('rejects a non probe-verified trust_state', () => {
  assert.deepEqual(validateUploadRecord(record({ trust_state: 'provider-list-observed' })), {
    ok: false,
    reason: 'not_probe_verified',
  });
});

test('rejects a non-allowlisted (private) base URL', () => {
  assert.deepEqual(
    validateUploadRecord(record({ normalized_public_base_url: 'https://llm.mycompany.internal/v1' })),
    { ok: false, reason: 'non_allowlisted_base_url' },
  );
});

test('rejects a bare fingerprint without its plaintext URL (de-anonymization guard)', () => {
  assert.deepEqual(
    validateUploadRecord(record({ normalized_public_base_url: null, endpoint_fingerprint: 'deadbeef' })),
    { ok: false, reason: 'bare_fingerprint_without_plaintext' },
  );
});

test('accepts a record that dropped its endpoint identity entirely', () => {
  assert.deepEqual(
    validateUploadRecord(record({ normalized_public_base_url: null, endpoint_fingerprint: null })),
    { ok: true },
  );
});

test('accepts public transit/aggregator hosts (openrouter + 七牛 Qiniu)', () => {
  for (const base of [
    'https://openrouter.ai/api/v1',
    'https://api.qnaigc.com/v1',
    'https://anthropic.qnaigc.com',
  ]) {
    assert.deepEqual(validateUploadRecord(record({ normalized_public_base_url: base })), { ok: true }, base);
  }
});

test('gate allowlist mirrors the qiniu transit hosts', () => {
  assert.ok(PUBLIC_PROVIDER_HOST_ALLOWLIST.has('api.qnaigc.com'));
  assert.ok(PUBLIC_PROVIDER_HOST_ALLOWLIST.has('anthropic.qnaigc.com'));
});

test('screenBatch partitions accepted vs rejected and never throws', () => {
  const { accepted, rejected } = screenBatch([record(), record({ api_key: 'x' }), 'not-an-object', null]);
  assert.equal(accepted.length, 1);
  assert.equal(rejected.length, 3);
});
