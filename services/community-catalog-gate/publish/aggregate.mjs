// Community Probe Catalog — publishing aggregator (runs in the scheduled Action).
//
// This is the ONLY component that writes the public catalog repo, and it does so
// via the Action's minimal `contents: write` token — NOT the gate. It:
//   1. reads buffered accepted records (drained from the gate's KV into a file),
//   2. drops withdrawn receipts and dedupes,
//   3. shards them, computes a SHA-256 per shard,
//   4. builds a manifest and signs its exact bytes with Ed25519 (raw 64-byte
//      signature, hex) so the desktop client can verify with the raw public key.
//
// Pure helpers are exported for testing; main() is the CLI used by the Action.

import { createHash, createPrivateKey, createPublicKey, generateKeyPairSync, sign } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const SHARD_SIZE = 500;

function sha256Hex(buffer) {
  return createHash('sha256').update(buffer).digest('hex');
}

// Stable identity for a record, used for dedupe across batches.
function recordKey(record) {
  return [
    record.provider_id || '',
    record.provider_model_id || '',
    record.endpoint_fingerprint || '',
    record.method_id || '',
    record.capability_family || '',
  ].join('|');
}

export function dedupeRecords(records) {
  const seen = new Map();
  for (const record of records) {
    seen.set(recordKey(record), record); // last write wins (freshest evidence)
  }
  return [...seen.values()];
}

// Public, content-addressed evidence id. Clients never upload an id (privacy);
// the publisher derives a stable one from the record identity so that dedupe and
// the client cache agree, and so the client's parse_catalog_evidence — which
// REQUIRES evidence_id — can consume the record. NOT a local/user id.
export function deriveEvidenceId(record) {
  return `cat-${sha256Hex(Buffer.from(recordKey(record), 'utf-8'))}`;
}

// Build the catalog: returns the manifest bytes (to be signed) + shard files.
// generatedAt is injected (no implicit clock) so callers control determinism.
export function buildCatalog(records, { protocolMajor, generatedAt }) {
  const deduped = dedupeRecords(records).map((record) => ({
    ...record,
    evidence_id: deriveEvidenceId(record),
  }));
  const shards = [];
  const shardFiles = [];
  for (let i = 0; i < deduped.length; i += SHARD_SIZE) {
    const chunk = deduped.slice(i, i + SHARD_SIZE);
    const path = `shards/shard-${shards.length}.json`;
    const body = Buffer.from(JSON.stringify({ records: chunk }), 'utf-8');
    shards.push({ path, sha256: sha256Hex(body), record_count: chunk.length });
    shardFiles.push({ path, body });
  }
  const manifest = { protocol_major: protocolMajor, generated_at: generatedAt, shards };
  const manifestBytes = Buffer.from(JSON.stringify(manifest), 'utf-8');
  return { manifestBytes, shardFiles };
}

// Sign exact manifest bytes with an Ed25519 PEM private key -> raw 64-byte hex.
export function signManifest(manifestBytes, privateKeyPem) {
  const key = createPrivateKey(privateKeyPem);
  return sign(null, manifestBytes, key).toString('hex');
}

// Derive the raw 32-byte public key (hex) the desktop client must be configured
// with, from a PEM private key.
export function rawPublicKeyHex(privateKeyPem) {
  const jwk = createPublicKey(createPrivateKey(privateKeyPem)).export({ format: 'jwk' });
  return Buffer.from(jwk.x, 'base64url').toString('hex');
}

export function generateSigningKeypair() {
  const { privateKey, publicKey } = generateKeyPairSync('ed25519');
  const privateKeyPem = privateKey.export({ type: 'pkcs8', format: 'pem' });
  const jwk = publicKey.export({ format: 'jwk' });
  return { privateKeyPem, publicKeyHex: Buffer.from(jwk.x, 'base64url').toString('hex') };
}

function main() {
  const mode = process.argv[2];
  if (mode === 'keygen') {
    const { privateKeyPem, publicKeyHex } = generateSigningKeypair();
    process.stdout.write(`# Store this PEM as the Action secret CATALOG_SIGNING_PRIVATE_KEY_PEM:\n`);
    process.stdout.write(`${privateKeyPem}\n`);
    process.stdout.write(`# Configure the desktop client (STUDIO_COMMUNITY_CATALOG_SIGNING_PUBKEY):\n`);
    process.stdout.write(`${publicKeyHex}\n`);
    return;
  }

  const inputFile = process.env.INPUT_RECORDS_FILE;
  const outDir = process.env.CATALOG_OUTPUT_DIR;
  const pem = process.env.CATALOG_SIGNING_PRIVATE_KEY_PEM;
  const protocolMajor = Number(process.env.PROTOCOL_MAJOR || '1');
  const generatedAt = process.env.GENERATED_AT;
  if (!inputFile || !outDir || !pem || !generatedAt) {
    throw new Error('INPUT_RECORDS_FILE, CATALOG_OUTPUT_DIR, CATALOG_SIGNING_PRIVATE_KEY_PEM, GENERATED_AT are required');
  }

  const parsed = JSON.parse(readFileSync(inputFile, 'utf-8'));
  const withdrawn = new Set(parsed.withdrawn_receipts || []);
  const records = (parsed.entries || [])
    .filter((entry) => !withdrawn.has(entry.receipt_token))
    .flatMap((entry) => entry.records || []);

  const { manifestBytes, shardFiles } = buildCatalog(records, { protocolMajor, generatedAt });
  const signatureHex = signManifest(manifestBytes, pem);

  mkdirSync(join(outDir, 'shards'), { recursive: true });
  for (const shard of shardFiles) {
    writeFileSync(join(outDir, shard.path), shard.body);
  }
  writeFileSync(join(outDir, 'manifest.json'), manifestBytes);
  writeFileSync(join(outDir, 'manifest.json.sig'), signatureHex);
  process.stdout.write(`Published ${records.length} records across ${shardFiles.length} shard(s).\n`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}
