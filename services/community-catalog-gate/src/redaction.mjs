// Community Probe Catalog gate — server-side redaction re-validation.
//
// Defense in depth: even though the desktop client sanitizes evidence before
// upload, the gate independently re-validates every record and REJECTS anything
// that could carry a secret, a private endpoint, or a bare un-salted hash. The
// gate is allowlist-only: a record may contain exactly these fields and nothing
// else.

export const ALLOWED_FIELDS = new Set([
  'evidence_type',
  'trust_state',
  'provider_id',
  'normalized_public_base_url',
  'endpoint_fingerprint',
  'route_key',
  'provider_model_id',
  'model_id',
  'method_id',
  'request_mapper_id',
  'capability_family',
  'model_type',
  'input_modalities',
  'output_modalities',
  'probe_status',
  'observed_at',
]);

// Must mirror the desktop client's PUBLIC_PROVIDER_HOST_ALLOWLIST. Two same-risk
// classes: official first-party endpoints AND public AI transit/aggregators that
// anyone can register and connect to (their base URLs are public domains carrying
// no user identity).
export const PUBLIC_PROVIDER_HOST_ALLOWLIST = new Set([
  // Official first-party provider endpoints.
  'api.openai.com',
  'api.anthropic.com',
  'generativelanguage.googleapis.com',
  'ark.cn-beijing.volces.com',
  'api.deepseek.com',
  'api.mistral.ai',
  'api.groq.com',
  'api.together.xyz',
  'api.x.ai',
  'dashscope.aliyuncs.com',
  'open.bigmodel.cn',
  'api.moonshot.cn',
  // Public AI transit / aggregators.
  'openrouter.ai',
  'api.qnaigc.com', // 七牛 Qiniu AI 中转 (OpenAI-compatible)
  'anthropic.qnaigc.com', // 七牛 Qiniu AI 中转 (Anthropic-compatible)
]);

export const WIRE_EVIDENCE_TYPE = 'probe_result';
export const UPLOADABLE_TRUST_STATE = 'probe-verified';

function hostOf(url) {
  try {
    return new URL(url).host.toLowerCase();
  } catch {
    return null;
  }
}

// Returns { ok: true } for an acceptable record, or { ok: false, reason } when
// the record must be rejected. The gate drops rejected records (counts them).
export function validateUploadRecord(record) {
  if (record === null || typeof record !== 'object' || Array.isArray(record)) {
    return { ok: false, reason: 'not_an_object' };
  }
  for (const key of Object.keys(record)) {
    if (!ALLOWED_FIELDS.has(key)) {
      return { ok: false, reason: `forbidden_field:${key}` };
    }
  }
  if (record.evidence_type !== WIRE_EVIDENCE_TYPE) {
    return { ok: false, reason: 'wrong_evidence_type' };
  }
  if (record.trust_state !== UPLOADABLE_TRUST_STATE) {
    return { ok: false, reason: 'not_probe_verified' };
  }
  const base = record.normalized_public_base_url;
  if (base !== undefined && base !== null) {
    const host = hostOf(base);
    if (host === null || !PUBLIC_PROVIDER_HOST_ALLOWLIST.has(host)) {
      return { ok: false, reason: 'non_allowlisted_base_url' };
    }
  }
  // A fingerprint may only ride along with its plaintext URL; a bare hash of a
  // private host must never be accepted (de-anonymization risk).
  if (
    record.endpoint_fingerprint !== undefined &&
    record.endpoint_fingerprint !== null &&
    (base === undefined || base === null)
  ) {
    return { ok: false, reason: 'bare_fingerprint_without_plaintext' };
  }
  return { ok: true };
}

// Partition a batch into accepted/rejected, never throwing.
export function screenBatch(records) {
  const accepted = [];
  const rejected = [];
  for (const record of Array.isArray(records) ? records : []) {
    const verdict = validateUploadRecord(record);
    if (verdict.ok) {
      accepted.push(record);
    } else {
      rejected.push({ reason: verdict.reason });
    }
  }
  return { accepted, rejected };
}
