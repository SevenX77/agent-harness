// Gate request-handler tests. The gate is a CLEAN OPEN API: clients send only a
// sanitized batch (no token, no credentials of any kind). All abuse control is
// server-side — re-screening (redaction.mjs) + per-client rate limiting. These
// tests pin that contract: ingestion needs no Authorization header, and the gate
// sheds load via the RATE_LIMITER binding.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { handleBatch, handleWithdraw } from '../src/gate.mjs';
import { UPLOADABLE_TRUST_STATE, WIRE_EVIDENCE_TYPE } from '../src/redaction.mjs';

function kv() {
  return {
    store: {},
    async get(k) {
      return Object.prototype.hasOwnProperty.call(this.store, k) ? this.store[k] : null;
    },
    async put(k, v) {
      this.store[k] = v;
    },
  };
}

function baseEnv(extra = {}) {
  return { PROTOCOL_MAJOR: '1', BUFFER: kv(), IDEMPOTENCY: kv(), WITHDRAWN: kv(), ...extra };
}

function validRecord(overrides = {}) {
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

function batchRequest(records, { idempotencyKey = 'k1' } = {}) {
  // Deliberately NO Authorization header — the open API takes none.
  return new Request('https://gate.example/v1/evidence/batches', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'idempotency-key': idempotencyKey },
    body: JSON.stringify({ protocol_major: 1, records }),
  });
}

test('batch is accepted with NO Authorization header (open API)', async () => {
  const env = baseEnv();
  const res = await handleBatch(batchRequest([validRecord()]), env);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.accepted, 1);
  assert.equal(body.rejected, 0);
  assert.equal(typeof body.receipt_token, 'string');
  // Buffered for the publishing Action to drain.
  assert.equal(Object.keys(env.BUFFER.store).length, 1);
});

test('batch is rejected with 429 when the rate limiter sheds it', async () => {
  const env = baseEnv({ RATE_LIMITER: { async limit() { return { success: false }; } } });
  const res = await handleBatch(batchRequest([validRecord()]), env);
  assert.equal(res.status, 429);
  // Nothing buffered when shed.
  assert.equal(Object.keys(env.BUFFER.store).length, 0);
});

test('batch proceeds when the rate limiter allows it', async () => {
  const env = baseEnv({ RATE_LIMITER: { async limit() { return { success: true }; } } });
  const res = await handleBatch(batchRequest([validRecord()]), env);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.accepted, 1);
});

test('withdraw is recorded with NO Authorization header (open API)', async () => {
  const env = baseEnv();
  const req = new Request('https://gate.example/v1/evidence/withdraw', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ receipt_token: 'rcpt-xyz' }),
  });
  const res = await handleWithdraw(req, env);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.status, 'withdrawal_recorded');
  assert.equal(await env.WITHDRAWN.get('rcpt-xyz'), '1');
});
