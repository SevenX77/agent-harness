// Community Probe Catalog gate — serverless ingestion endpoint.
//
// SECURITY MODEL (clean open API — all abuse control is server-side):
//   - The CLIENT sends only a sanitized batch: no token, no credentials, no
//     repo write key. There is nothing secret to configure or leak client-side.
//   - The gate holds NO catalog-repo write token. It only writes to its own KV
//     buffer. Publishing to the public catalog repo is done by a SEPARATE
//     scheduled GitHub Action with minimal `contents: write` (see publish/).
//   - Every record is re-validated server-side (src/redaction.mjs) and rejected
//     if it could carry a secret, a private endpoint, or a bare hash.
//   - Abuse is contained server-side by per-client RATE LIMITING (not a shared
//     token — any client could extract one anyway): the Cloudflare RATE_LIMITER
//     binding sheds excess requests; redaction caps what any request can land.
//   - Idempotency-Key dedupes retries; receipt_token enables later withdrawal.
//
// Deploy as a Cloudflare Worker (wrangler). Bindings (see README):
//   env.RATE_LIMITER     — Cloudflare rate-limit binding (per-client shedding)
//   env.PROTOCOL_MAJOR   — accepted wire protocol major (string int)
//   env.BUFFER           — KV namespace: pending accepted records
//   env.IDEMPOTENCY      — KV namespace: idempotency-key -> ack
//   env.WITHDRAWN        — KV namespace: receipt_token -> 1

import { screenBatch } from './redaction.mjs';

const BATCH_PATH = '/v1/evidence/batches';
const WITHDRAW_PATH = '/v1/evidence/withdraw';
const MAX_BATCH = 500;

// TTL for BUFFER (`pending/*`) and WITHDRAWN entries. Without this they were
// write-only: nothing in the system ever deletes them, so both namespaces grew
// forever (found 2026-08-23).
//
// The obvious fix in a queue system is "consumer deletes on ack" — Cloudflare
// Queues and SQS both work that way. It does not apply here: that pattern
// needs the consumer to hold WRITE power on the queue, and the publishing
// Action is deliberately handed only a READ-ONLY KV token (see
// `publish/publish-catalog.yml`'s `CF_API_TOKEN` comment, and `drain-kv.mjs`,
// which only ever calls list/get) to cap the blast radius of a leaked Action
// secret. Instead we use TTL-based self-expiry, the standard KV-as-queue idiom
// on Cloudflare, and the same mechanism already used a few lines below for
// IDEMPOTENCY — this just extends it to the two namespaces that were missing it.
//
// Trade-off this accepts: if the publishing Action stays broken for more than
// 30 days, any still-unpublished entries expire and are lost. The publish cron
// runs every 6 hours (`publish/publish-catalog.yml`), so 30 days is ~120 missed
// cycles of headroom, and a broken Action shows red in GitHub Actions rather
// than failing silently. This TTL is NOT retroactive: keys already written
// before this change have no expiry and need a one-off sweep with a
// WRITE-capable KV token (out of scope here — the gate/Action only ever hold
// read-only or no KV write power by design; see README "Operations").
const PENDING_ENTRY_TTL_SECONDS = 60 * 60 * 24 * 30; // 30 days

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

// Server-side abuse control. With no client token, the only line between "Studio
// contributing" and "anyone flooding the gate" is per-client shedding. The
// RATE_LIMITER binding is keyed on the real client IP; absent (local/test) it
// allows through so unit tests need no Cloudflare runtime.
async function rateLimited(request, env) {
  if (!env.RATE_LIMITER) return false;
  const key = request.headers.get('cf-connecting-ip') || 'anonymous';
  const { success } = await env.RATE_LIMITER.limit({ key });
  return !success;
}

async function handleBatch(request, env) {
  if (await rateLimited(request, env)) {
    return json({ error: 'rate_limited' }, 429);
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
      { expirationTtl: PENDING_ENTRY_TTL_SECONDS },
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
  if (await rateLimited(request, env)) {
    return json({ error: 'rate_limited' }, 429);
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
    // Same TTL as the BUFFER entry it marks: a withdrawal record is only
    // meaningful while the buffer entry it excludes could still be drained,
    // so the two are given the same lifetime.
    await env.WITHDRAWN.put(String(receiptToken), '1', {
      expirationTtl: PENDING_ENTRY_TTL_SECONDS,
    });
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
