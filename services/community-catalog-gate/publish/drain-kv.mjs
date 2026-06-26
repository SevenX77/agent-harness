// Drain the gate's Cloudflare KV buffer into a records file for aggregate.mjs.
//
// Runs in the scheduled Action (read-only KV API token). It lists the BUFFER
// namespace under `pending/`, fetches each entry, collects withdrawn receipts
// from the WITHDRAWN namespace, and writes { entries, withdrawn_receipts } to
// INPUT_RECORDS_FILE. This is network code (Cloudflare KV REST API) and is not
// unit-tested; the data it produces is consumed by the tested aggregate.mjs.

import { writeFileSync } from 'node:fs';

const API = 'https://api.cloudflare.com/client/v4';

function env(name) {
  const value = process.env[name];
  if (!value) throw new Error(`missing env ${name}`);
  return value;
}

async function cf(path) {
  const response = await fetch(`${API}${path}`, {
    headers: { Authorization: `Bearer ${env('CF_API_TOKEN')}` },
  });
  if (!response.ok) throw new Error(`cloudflare api ${path} -> ${response.status}`);
  return response;
}

async function listKeys(accountId, namespaceId, prefix) {
  const keys = [];
  let cursor = '';
  do {
    const qs = new URLSearchParams({ prefix, limit: '1000' });
    if (cursor) qs.set('cursor', cursor);
    const body = await (await cf(`/accounts/${accountId}/storage/kv/namespaces/${namespaceId}/keys?${qs}`)).json();
    for (const item of body.result || []) keys.push(item.name);
    cursor = body.result_info?.cursor || '';
  } while (cursor);
  return keys;
}

async function getValue(accountId, namespaceId, key) {
  const response = await cf(
    `/accounts/${accountId}/storage/kv/namespaces/${namespaceId}/values/${encodeURIComponent(key)}`,
  );
  return response.text();
}

async function main() {
  const accountId = env('CF_ACCOUNT_ID');
  const bufferNs = env('CF_BUFFER_NAMESPACE_ID');
  const withdrawnNs = env('CF_WITHDRAWN_NAMESPACE_ID');
  const outFile = env('INPUT_RECORDS_FILE');

  const entryKeys = await listKeys(accountId, bufferNs, 'pending/');
  const entries = [];
  for (const key of entryKeys) {
    entries.push(JSON.parse(await getValue(accountId, bufferNs, key)));
  }
  const withdrawnReceipts = await listKeys(accountId, withdrawnNs, '');

  writeFileSync(outFile, JSON.stringify({ entries, withdrawn_receipts: withdrawnReceipts }, null, 2));
  process.stdout.write(`Drained ${entries.length} buffered entr(y/ies); ${withdrawnReceipts.length} withdrawn.\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exit(1);
});
