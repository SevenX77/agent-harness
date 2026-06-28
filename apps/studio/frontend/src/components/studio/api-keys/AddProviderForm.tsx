import { useState, type FormEvent } from "react"
import { Plus, Trash2 } from "lucide-react"
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
  baseUrls?: string[]
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
    baseUrls: [""],
    apiKey: "",
    type: "third-party",
  }
}

export function deriveAddProviderFormSubmission({
  customName,
  customBaseUrl,
  customBaseUrls,
  apiKey,
}: {
  type?: AddProviderType
  customName: string
  customBaseUrl: string
  customBaseUrls?: string[]
  apiKey: string
}): AddProviderFormSubmission {
  const baseUrls = customBaseUrls?.length ? customBaseUrls : [customBaseUrl]
  return {
    providerCode: providerCodeFromCustomName(customName),
    name: customName,
    baseUrl: baseUrls[0] ?? "",
    baseUrls,
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

function newBaseUrlRowId(): string {
  return `base-url-${newProviderCodeSuffix()}`
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
 * One-step third-party provider form (atom-19): name + api_key + base_urls filled
 * in a single inline form, replacing the old two-step name-only dialog. Protocol
 * is NOT asked here — it is auto-detected at test time (#24/#25). The api_key
 * field is always type=text. The field stays readable while typing; saved
 * ProviderCard secrets are masked only in the idle hidden state.
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
  const [baseUrlRows, setBaseUrlRows] = useState([{ id: "primary", value: "" }])
  const [apiKey, setApiKey] = useState("")
  const [submitAttempted, setSubmitAttempted] = useState(false)
  const nameError = addProviderNameError(name, existingNames)

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitAttempted(true)
    if (nameError) return
    const enteredBaseUrls = baseUrlRows.map((row) => row.value.trim())
    const baseUrls = enteredBaseUrls.some(Boolean) ? enteredBaseUrls.filter(Boolean) : [""]
    onSubmit({
      providerCode: `custom-${newProviderCodeSuffix()}`,
      name: name.trim(),
      baseUrl: baseUrls[0] ?? "",
      baseUrls,
      apiKey,
      type: "third-party",
    })
  }

  function updateBaseUrlRow(rowId: string, value: string) {
    setBaseUrlRows((current) => current.map((row) => (
      row.id === rowId ? { ...row, value } : row
    )))
  }

  function addBaseUrlRow() {
    setBaseUrlRows((current) => [...current, { id: newBaseUrlRowId(), value: "" }])
  }

  function removeBaseUrlRow(rowId: string) {
    setBaseUrlRows((current) => (
      current.length > 1 ? current.filter((row) => row.id !== rowId) : current
    ))
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
        <FieldLabel htmlFor="add-provider-api-key">{t("apiKeys.form.apiKeyLabel")}</FieldLabel>
        <Input
          id="add-provider-api-key"
          type={apiKeyInputType()}
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder={t("apiKeys.form.apiKeyPlaceholder")}
          className={cn(apiKeyInputClassName(true, Boolean(apiKey), { cssMask: false }), "h-8 text-xs")}
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="none"
          data-1p-ignore=""
          data-lpignore="true"
          data-form-type="other"
        />
      </Field>
      <Field>
        <FieldLabel htmlFor="add-provider-base-url">{t("apiKeys.form.baseUrlLabel")}</FieldLabel>
        <div className="space-y-2">
          {baseUrlRows.map((row, index) => (
            <div key={row.id} className="flex items-center gap-1.5">
              <Input
                id={index === 0 ? "add-provider-base-url" : `add-provider-base-url-${row.id}`}
                value={row.value}
                onChange={(event) => updateBaseUrlRow(row.id, event.target.value)}
                placeholder={index === 0 ? t("apiKeys.card.baseUrlPlaceholder1") : t("apiKeys.card.baseUrlPlaceholder2")}
                className="h-8 text-xs"
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="none"
                spellCheck={false}
              />
              {baseUrlRows.length > 1 ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-8 shrink-0 text-muted-foreground/70 transition-none hover:text-destructive [&_svg]:size-3.5"
                  onClick={() => removeBaseUrlRow(row.id)}
                  aria-label={t("apiKeys.card.removeBaseUrlButton")}
                >
                  <Trash2 />
                </Button>
              ) : null}
            </div>
          ))}
          <Button type="button" variant="outline" size="sm" onClick={addBaseUrlRow} className="gap-1">
            <Plus className="size-3.5" />
            {t("apiKeys.card.addUrlButton")}
          </Button>
        </div>
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
