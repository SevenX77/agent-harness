// Community Probe Catalog — write-path publisher (runs in the scheduled Action).
//
// This REPLACES the Cloudflare-KV drain for the no-gate deployment. The desktop
// pushes sanitized evidence batches into the repo's `incoming/` staging area; this
// script re-validates every NEW record server-side (defense in depth) and merges
// the survivors with the records already published in `shards/`, then rebuilds and
// signs the catalog exactly like aggregate.mjs.
//
// Security model is unchanged from the gate design:
//   - The signing key lives ONLY as the Action secret CATALOG_SIGNING_PRIVATE_KEY_PEM.
//   - Every incoming record is screened (src/redaction.mjs); dirty records (secrets,
//     private endpoints, non probe-verified, bare hashes) are dropped and counted.
//   - Already-published records bypass screening: they carry a publisher-stamped
//     evidence_id (not an upload-allowlisted field) and were screened on the way in.
//
// Pure helpers are exported for testing; main() is the CLI used by the Action.

import { mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { screenBatch } from '../src/redaction.mjs';
import { buildCatalog, signManifest } from './aggregate.mjs';

// Merge already-published shard records with screened incoming batches.
// existingShards / incomingBatches are arrays of { records: [...] } objects.
// Returns { records, accepted (count), rejected ([{reason}]) }.
export function mergeRecords({ existingShards = [], incomingBatches = [] }) {
  const recordsOf = (container) =>
    container && Array.isArray(container.records) ? container.records : [];
  const existingRecords = existingShards.flatMap(recordsOf);
  const incomingRecords = incomingBatches.flatMap(recordsOf);
  const { accepted, rejected } = screenBatch(incomingRecords);
  return { records: [...existingRecords, ...accepted], accepted: accepted.length, rejected };
}

function readJsonDir(dir) {
  let names;
  try {
    names = readdirSync(dir);
  } catch {
    return []; // missing dir => nothing to read
  }
  const files = [];
  for (const name of names.sort()) {
    if (!name.endsWith('.json')) continue;
    const path = join(dir, name);
    files.push({ path, name, body: JSON.parse(readFileSync(path, 'utf-8')) });
  }
  return files;
}

function main() {
  const repoDir = process.env.CATALOG_OUTPUT_DIR;
  const pem = process.env.CATALOG_SIGNING_PRIVATE_KEY_PEM;
  const protocolMajor = Number(process.env.PROTOCOL_MAJOR || '1');
  const generatedAt = process.env.GENERATED_AT;
  if (!repoDir || !pem || !generatedAt) {
    throw new Error('CATALOG_OUTPUT_DIR, CATALOG_SIGNING_PRIVATE_KEY_PEM, GENERATED_AT are required');
  }

  const existingShards = readJsonDir(join(repoDir, 'shards')).map((f) => f.body);
  const incomingFiles = readJsonDir(join(repoDir, 'incoming'));
  const incomingBatches = incomingFiles.map((f) => f.body);

  const { records, accepted, rejected } = mergeRecords({ existingShards, incomingBatches });
  const { manifestBytes, shardFiles } = buildCatalog(records, { protocolMajor, generatedAt });
  const signatureHex = signManifest(manifestBytes, pem);

  mkdirSync(join(repoDir, 'shards'), { recursive: true });
  for (const shard of shardFiles) {
    writeFileSync(join(repoDir, shard.path), shard.body);
  }
  writeFileSync(join(repoDir, 'manifest.json'), manifestBytes);
  writeFileSync(join(repoDir, 'manifest.json.sig'), signatureHex);

  // Consume the staging area so the same batch is not re-ingested next run.
  for (const file of incomingFiles) {
    rmSync(file.path);
  }

  // Report the DEDUPED total actually written (manifest record_counts), not the
  // pre-dedupe merged length — re-pushing already-published evidence is a no-op,
  // and the log must say so honestly rather than imply spurious growth.
  const publishedCount = JSON.parse(manifestBytes.toString()).shards.reduce(
    (total, shard) => total + shard.record_count,
    0,
  );
  process.stdout.write(
    `Screened-in ${accepted} incoming record(s); rejected ${rejected.length}; ` +
      `published ${publishedCount} unique record(s) total across ${shardFiles.length} shard(s); ` +
      `consumed ${incomingFiles.length} incoming file(s).\n`,
  );
  if (rejected.length) {
    process.stdout.write(`Rejected reasons: ${JSON.stringify(rejected)}\n`);
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}
