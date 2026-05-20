export interface ProviderAvailabilityInput {
  api_key: string
  last_test_status?: string
}

/**
 * Categorise a model's runnable state based on its provider chain (F6).
 *
 * - `ok`           — at least one provider has a stored key AND the most
 *                    recent Test came back `ok`. The model is ready to run.
 * - `key_only`     — providers have keys but none have passed a Test. The
 *                    model *might* run; surface as a soft warning.
 * - `unavailable`  — no provider in the chain has a stored key, so the
 *                    engine has nothing to route to.
 *
 * The badge shown in the dropdown options follows the same enum.
 */
export type ModelAvailability = "ok" | "key_only" | "unavailable"

export function getModelAvailability(
  providers: ReadonlyArray<string>,
  credentialsByCode: Readonly<Record<string, ProviderAvailabilityInput | undefined>>,
): ModelAvailability {
  let sawKey = false
  for (const code of providers) {
    const credential = credentialsByCode[code]
    if (!credential?.api_key.trim()) continue
    sawKey = true
    if (credential.last_test_status === "ok") return "ok"
  }
  return sawKey ? "key_only" : "unavailable"
}
