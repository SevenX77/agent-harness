// Publishing aggregator tests: dedupe, content-addressed evidence ids, sharding
// with per-shard digests, and the Ed25519 sign/verify contract the desktop client
// relies on (raw 32-byte public key, raw 64-byte signature as hex).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash, createPublicKey, verify } from 'node:crypto';
import {
  buildCatalog,
  dedupeRecords,
  deriveEvidenceId,
  generateSigningKeypair,
  rawPublicKeyHex,
  signManifest,
} from '../publish/aggregate.mjs';

function rec(overrides = {}) {
  return {
    provider_id: 'openai',
    provider_model_id: 'gpt-4o',
    endpoint_fingerprint: 'fp-openai',
    method_id: 'chat.completions',
    capability_family: 'text',
    ...overrides,
  };
}

const OPTS = { protocolMajor: 1, generatedAt: '2026-06-26T00:00:00Z' };

test('dedupeRecords collapses identical identities (last write wins)', () => {
  const out = dedupeRecords([
    rec({ probe_status: 'old' }),
    rec({ probe_status: 'fresh' }),
    rec({ provider_model_id: 'gpt-3.5' }),
  ]);
  assert.equal(out.length, 2);
  const gpt4o = out.find((r) => r.provider_model_id === 'gpt-4o');
  assert.equal(gpt4o.probe_status, 'fresh');
});

test('deriveEvidenceId is stable, distinct per identity, and content-addressed', () => {
  assert.equal(deriveEvidenceId(rec()), deriveEvidenceId(rec()));
  assert.notEqual(deriveEvidenceId(rec()), deriveEvidenceId(rec({ provider_model_id: 'other' })));
  assert.match(deriveEvidenceId(rec()), /^cat-[0-9a-f]{64}$/);
});

test('buildCatalog stamps an evidence_id on every record and digests each shard', () => {
  const { manifestBytes, shardFiles } = buildCatalog([rec(), rec({ provider_model_id: 'gpt-3.5' })], OPTS);
  const manifest = JSON.parse(manifestBytes.toString('utf-8'));
  assert.equal(manifest.protocol_major, 1);
  assert.equal(manifest.generated_at, OPTS.generatedAt);
  assert.equal(manifest.shards.length, 1);

  const { records } = JSON.parse(shardFiles[0].body.toString('utf-8'));
  assert.equal(records.length, 2);
  for (const r of records) assert.match(r.evidence_id, /^cat-[0-9a-f]{64}$/);
  assert.equal(new Set(records.map((r) => r.evidence_id)).size, 2);

  const digest = createHash('sha256').update(shardFiles[0].body).digest('hex');
  assert.equal(manifest.shards[0].sha256, digest);
  assert.equal(manifest.shards[0].record_count, 2);
});

test('signManifest yields a raw 64-byte hex signature the raw public key verifies', () => {
  const { privateKeyPem, publicKeyHex } = generateSigningKeypair();
  const { manifestBytes } = buildCatalog([rec()], OPTS);
  const sigHex = signManifest(manifestBytes, privateKeyPem);
  assert.match(sigHex, /^[0-9a-f]{128}$/);

  const pubKey = createPublicKey({
    key: { kty: 'OKP', crv: 'Ed25519', x: Buffer.from(publicKeyHex, 'hex').toString('base64url') },
    format: 'jwk',
  });
  assert.equal(verify(null, manifestBytes, pubKey, Buffer.from(sigHex, 'hex')), true);
  // A tampered manifest must fail verification (fail-closed read path).
  const tampered = Buffer.concat([manifestBytes, Buffer.from('x')]);
  assert.equal(verify(null, tampered, pubKey, Buffer.from(sigHex, 'hex')), false);
});

test('rawPublicKeyHex matches the keypair public key', () => {
  const { privateKeyPem, publicKeyHex } = generateSigningKeypair();
  assert.equal(rawPublicKeyHex(privateKeyPem), publicKeyHex);
});
