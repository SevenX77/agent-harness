import { useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import i18n from "@/i18n"
import { cn } from "@/lib/utils"
import { apiKeyInputClassName, apiKeyInputType } from "./ProviderCard"

export type AddProviderType = "third-party"
export const newProviderName = "New Provider"

export interface AddProviderFormSubmission {
  providerCode: string
  name: string
  baseUrl: string
  apiKey: string
  type: AddProviderType
}

export function providerCodeFromCustomName(customName: string): string {
  return customName.toLowerCase().replace(/[^a-z0-9]/g, "-")
}

export function createBlankAddProviderSubmission(): AddProviderFormSubmission {
  return {
    providerCode: `custom-${newProviderCodeSuffix()}`,
    name: newProviderName,
    baseUrl: "",
    apiKey: "",
    type: "third-party",
  }
}

export function deriveAddProviderFormSubmission({
  customName,
  customBaseUrl,
  apiKey,
}: {
  type?: AddProviderType
  customName: string
  customBaseUrl: string
  apiKey: string
}): AddProviderFormSubmission {
  return {
    providerCode: providerCodeFromCustomName(customName),
    name: customName,
    baseUrl: customBaseUrl,
    apiKey,
    type: "third-party",
  }
}

let providerCodeFallbackCounter = 0

function newProviderCodeSuffix(): string {
  const uuid = globalThis.crypto?.randomUUID?.()
  if (uuid) return uuid
  providerCodeFallbackCounter += 1
  return `${Date.now()}-${providerCodeFallbackCounter}`
}

export function addProviderNameError(name: string, existingNames: string[]): string | null {
  const trimmed = name.trim()
  if (!trimmed) return i18n.t("apiKeys.form.providerNameRequired")
  if (existingNames.some((existing) => existing.trim().toLowerCase() === trimmed.toLowerCase())) {
    return i18n.t("apiKeys.form.providerNameDuplicate")
  }
  return null
}

/**
 * One-step third-party provider form (atom-19): name + base_url + api_key filled
 * in a single inline form, replacing the old two-step name-only dialog. Protocol
 * is NOT asked here — it is auto-detected at test time (#24/#25). The api_key
 * field is always type=text, and CSS masking is applied only after a value exists
 * so an empty placeholder remains readable (atom-22 contract).
 */
export function AddProviderForm({
  existingNames,
  onSubmit,
  onCancel,
}: {
  existingNames: string[]
  onSubmit: (submission: AddProviderFormSubmission) => void
  onCancel: () => void
}) {
  const { t } = useTranslation("settings")
  const [name, setName] = useState("")
  const [baseUrl, setBaseUrl] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [submitAttempted, setSubmitAttempted] = useState(false)
  const nameError = addProviderNameError(name, existingNames)

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitAttempted(true)
    if (nameError) return
    onSubmit({
      providerCode: `custom-${newProviderCodeSuffix()}`,
      name: name.trim(),
      baseUrl: baseUrl.trim(),
      apiKey,
      type: "third-party",
    })
  }

  return (
    <form
      data-add-provider-form="true"
      onSubmit={handleSubmit}
      className="space-y-3 rounded-md border border-dashed border-border/60 bg-muted/10 p-3"
    >
      <Field>
        <FieldLabel htmlFor="add-provider-name">{t("apiKeys.form.providerNameLabel")}</FieldLabel>
        <Input
          id="add-provider-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={t("apiKeys.form.providerNamePlaceholder")}
          className="h-8 text-xs"
          aria-invalid={submitAttempted && nameError ? true : undefined}
          autoFocus
        />
        {submitAttempted && nameError ? (
          <p className="text-xs text-destructive">{nameError}</p>
        ) : null}
      </Field>
      <Field>
        <FieldLabel htmlFor="add-provider-base-url">{t("apiKeys.form.baseUrlLabel")}</FieldLabel>
        <Input
          id="add-provider-base-url"
          value={baseUrl}
          onChange={(event) => setBaseUrl(event.target.value)}
          placeholder={t("apiKeys.form.baseUrlPlaceholder")}
          className="h-8 text-xs"
        />
      </Field>
      <Field>
        <FieldLabel htmlFor="add-provider-api-key">{t("apiKeys.form.apiKeyLabel")}</FieldLabel>
        <Input
          id="add-provider-api-key"
          type={apiKeyInputType()}
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder={t("apiKeys.form.apiKeyPlaceholder")}
          className={cn(apiKeyInputClassName(false, Boolean(apiKey)), "h-8 text-xs")}
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="none"
          data-1p-ignore=""
          data-lpignore="true"
          data-form-type="other"
        />
      </Field>
      <div className="flex gap-2">
        <Button type="submit" size="sm" data-add-provider-submit="true" className="gap-1">
          {t("apiKeys.add")}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          {t("apiKeys.form.cancelButton")}
        </Button>
      </div>
    </form>
  )
}
