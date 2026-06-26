// Community Probe Catalog gate — serverless ingestion endpoint.
//
// SECURITY MODEL (three-way converged design v3):
//   - The gate holds NO catalog-repo write token. It only writes to its own KV
//     buffer. Publishing to the public catalog repo is done by a SEPARATE
//     scheduled GitHub Action with minimal `contents: write` (see publish/).
//   - Every record is re-validated server-side (src/redaction.mjs) and rejected
//     if it could carry a secret, a private endpoint, or a bare hash.
//   - Uploads are opt-in: a request must carry a valid anonymous ingestion token.
//   - Idempotency-Key dedupes retries; receipt_token enables later withdrawal.
//
// Deploy as a Cloudflare Worker (wrangler). Bindings (see README):
//   env.INGESTION_TOKEN  — shared anonymous opt-in token (secret)
//   env.PROTOCOL_MAJOR   — accepted wire protocol major (string int)
//   env.BUFFER           — KV namespace: pending accepted records
//   env.IDEMPOTENCY      — KV namespace: idempotency-key -> ack
//   env.WITHDRAWN        — KV namespace: receipt_token -> 1

import { screenBatch } from './redaction.mjs';

const BATCH_PATH = '/v1/evidence/batches';
const WITHDRAW_PATH = '/v1/evidence/withdraw';
const MAX_BATCH = 500;

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function authorized(request, env) {
  const header = request.headers.get('authorization') || '';
  const token = header.startsWith('Bearer ') ? header.slice(7).trim() : '';
  return Boolean(env.INGESTION_TOKEN) && token === env.INGESTION_TOKEN;
}

async function handleBatch(request, env) {
  if (!authorized(request, env)) {
    return json({ error: 'unauthorized' }, 401);
  }
  const idempotencyKey = request.headers.get('idempotency-key') || '';
  if (idempotencyKey && env.IDEMPOTENCY) {
    const cached = await env.IDEMPOTENCY.get(idempotencyKey);
    if (cached) {
      return json(JSON.parse(cached)); // replay the prior ack — no double ingest
    }
  }

  let payload;
  try {
    payload = await request.json();
  } catch {
    return json({ error: 'invalid_json' }, 400);
  }
  if (String(payload?.protocol_major) !== String(env.PROTOCOL_MAJOR)) {
    return json({ error: 'protocol_major_mismatch' }, 409);
  }
  const records = Array.isArray(payload?.records) ? payload.records : [];
  if (records.length > MAX_BATCH) {
    return json({ error: 'batch_too_large', max: MAX_BATCH }, 413);
  }

  const { accepted, rejected } = screenBatch(records);
  const receiptToken = crypto.randomUUID();

  if (accepted.length > 0 && env.BUFFER) {
    // Buffer key sorts by time; the publishing Action drains it. No repo token here.
    const key = `pending/${Date.now()}-${receiptToken}`;
    await env.BUFFER.put(
      key,
      JSON.stringify({ receipt_token: receiptToken, records: accepted }),
    );
  }

  const ack = {
    accepted: accepted.length,
    rejected: rejected.length,
    receipt_token: receiptToken,
  };
  if (idempotencyKey && env.IDEMPOTENCY) {
    await env.IDEMPOTENCY.put(idempotencyKey, JSON.stringify(ack), {
      expirationTtl: 60 * 60 * 24 * 30,
    });
  }
  return json(ack);
}

async function handleWithdraw(request, env) {
  if (!authorized(request, env)) {
    return json({ error: 'unauthorized' }, 401);
  }
  let payload;
  try {
    payload = await request.json();
  } catch {
    return json({ error: 'invalid_json' }, 400);
  }
  const receiptToken = payload?.receipt_token;
  if (!receiptToken) {
    return json({ error: 'missing_receipt_token' }, 400);
  }
  if (env.WITHDRAWN) {
    await env.WITHDRAWN.put(String(receiptToken), '1');
  }
  return json({ status: 'withdrawal_recorded' });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'POST' && url.pathname === BATCH_PATH) {
      return handleBatch(request, env);
    }
    if (request.method === 'POST' && url.pathname === WITHDRAW_PATH) {
      return handleWithdraw(request, env);
    }
    return json({ error: 'not_found' }, 404);
  },
};

export { handleBatch, handleWithdraw };
