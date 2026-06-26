// publish-from-incoming: the write-path replacement for the Cloudflare-KV drain.
//
// Instead of draining a gate's KV buffer, the scheduled Action reads JSON batches
// that the desktop pushed into the repo's `incoming/` staging area, RE-VALIDATES
// every new record server-side (defense in depth — the desktop already sanitized
// once), and merges the survivors with the records already published in shards/.
// These tests pin the pure merge+screen behavior; the IO main() is the CLI.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mergeRecords } from '../publish/publish-from-incoming.mjs';

// A clean wire record as the desktop would push it (allowlisted fields only).
function wireRec(overrides = {}) {
  return {
    evidence_type: 'probe_result',
    trust_state: 'probe-verified',
    provider_model_id: 'gpt-4o',
    model_id: 'gpt-4o',
    method_id: 'chat.completions',
    capability_family: 'text',
    normalized_public_base_url: 'https://api.openai.com/v1',
    ...overrides,
  };
}

// An already-published record carries a publisher-stamped evidence_id.
function shardRec(overrides = {}) {
  return { ...wireRec(overrides), evidence_id: 'cat-existing' };
}

test('mergeRecords merges existing shards with screened incoming records', () => {
  const existingShards = [{ records: [shardRec({ provider_model_id: 'old-model' })] }];
  const incomingBatches = [{ records: [wireRec({ provider_model_id: 'new-model' })] }];
  const { records, accepted, rejected } = mergeRecords({ existingShards, incomingBatches });
  assert.equal(records.length, 2);
  assert.equal(accepted, 1);
  assert.deepEqual(rejected, []);
  assert.ok(records.some((r) => r.provider_model_id === 'old-model'));
  assert.ok(records.some((r) => r.provider_model_id === 'new-model'));
});

test('mergeRecords rejects a dirty incoming record carrying a forbidden field (possible secret)', () => {
  const incomingBatches = [{ records: [wireRec({ api_key: 'sk-LEAK' })] }];
  const { records, accepted, rejected } = mergeRecords({ existingShards: [], incomingBatches });
  assert.equal(records.length, 0);
  assert.equal(accepted, 0);
  assert.equal(rejected.length, 1);
  assert.match(rejected[0].reason, /^forbidden_field:/);
});

test('mergeRecords rejects a non probe-verified incoming record', () => {
  const incomingBatches = [{ records: [wireRec({ trust_state: 'provider-list-observed' })] }];
  const { accepted, rejected } = mergeRecords({ existingShards: [], incomingBatches });
  assert.equal(accepted, 0);
  assert.equal(rejected[0].reason, 'not_probe_verified');
});

test('mergeRecords rejects a private (non-allowlisted) base url', () => {
  const incomingBatches = [{ records: [wireRec({ normalized_public_base_url: 'https://llm.mycompany.internal/v1' })] }];
  const { accepted, rejected } = mergeRecords({ existingShards: [], incomingBatches });
  assert.equal(accepted, 0);
  assert.equal(rejected[0].reason, 'non_allowlisted_base_url');
});

test('mergeRecords leaves the catalog untouched when there is no incoming batch', () => {
  const existingShards = [{ records: [shardRec(), shardRec({ provider_model_id: 'b' })] }];
  const { records, accepted, rejected } = mergeRecords({ existingShards, incomingBatches: [] });
  assert.equal(records.length, 2);
  assert.equal(accepted, 0);
  assert.deepEqual(rejected, []);
});

test('mergeRecords does NOT re-screen already-published records (their evidence_id is allowed through)', () => {
  // A published record carries evidence_id, which is NOT in the upload allowlist.
  // Existing records must bypass screenBatch, or every republish would wipe them.
  const existingShards = [{ records: [shardRec()] }];
  const { records } = mergeRecords({ existingShards, incomingBatches: [] });
  assert.equal(records.length, 1);
  assert.equal(records[0].evidence_id, 'cat-existing');
});

test('mergeRecords tolerates malformed batches/shards without throwing', () => {
  const { records, accepted, rejected } = mergeRecords({
    existingShards: [{}, { records: null }],
    incomingBatches: [{}, { records: undefined }, { records: [wireRec()] }],
  });
  assert.equal(records.length, 1);
  assert.equal(accepted, 1);
  assert.deepEqual(rejected, []);
});
