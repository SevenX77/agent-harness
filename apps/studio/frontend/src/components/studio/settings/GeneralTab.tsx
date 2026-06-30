import { useEffect, useMemo, useRef, useState } from "react"
import { ChevronDown, Copy, ExternalLink, FolderOpen, RotateCcw } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  type CommunityCatalogConfig,
  getCommunityCatalogConfig,
  getTruthSourceContent,
  getTruthSources,
  type RuntimeActivityLogEntry,
  type TruthSource,
  type TruthSourceContentResponse,
  type TruthSourceSection,
} from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  CatalogAccordion,
  CatalogAccordionContent,
  CatalogAccordionItem,
  CatalogAccordionTrigger,
} from "@/components/ui/catalog-accordion"
import {
  Card,
  CardContent,
  CardHeader,
} from "@/components/ui/card"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { SaveStatusBadge } from "@/components/ui/save-status-badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import { openLocalPath, selectSkillDirectory } from "@/lib/tauri"
import { effectiveDefaultSkillsDirectory } from "@/utils/skill-paths"
import { applyLanguageChange } from "./language-switch"
import { SectionTitle } from "./shared"
import type { SettingsPageContentProps } from "./types"

const truthSourceFieldRowClassName = "grid w-full grid-cols-[minmax(0,1fr)_6.5rem] items-center gap-2"
const truthSourceFieldActionClassName = "flex min-w-0 items-center justify-center gap-2"
const truthSourceActionButtonClassName = "w-24"
const truthSourceScrollableInputClassName = "overflow-x-auto whitespace-nowrap text-clip text-muted-foreground"
const truthSourceCategoryLabelKeys = {
  settings: "general.truthSources.categories.settings",
  workspace: "general.truthSources.categories.workspace",
  credentials: "general.truthSources.categories.credentials",
  roles: "general.truthSources.categories.roles",
  health: "general.truthSources.categories.health",
  modelRules: "general.truthSources.categories.modelRules",
  diagnostics: "general.truthSources.categories.diagnostics",
  runtime: "general.truthSources.categories.runtime",
} as const

type TruthSourceCategory = keyof typeof truthSourceCategoryLabelKeys

export function GeneralTab({ appSettings }: Pick<SettingsPageContentProps, "appSettings">) {
  const { i18n, t } = useTranslation("settings")
  const [selectingDefaultFolder, setSelectingDefaultFolder] = useState(false)
  const [truthSections, setTruthSections] = useState<TruthSourceSection[]>([])
  const [truthSourcesLoading, setTruthSourcesLoading] = useState(false)
  const [truthSourcesError, setTruthSourcesError] = useState<string | null>(null)
  const [preview, setPreview] = useState<TruthSourceContentResponse | null>(null)
  const [catalogConfig, setCatalogConfig] = useState<CommunityCatalogConfig | null>(null)
  const fallbackDefaultSkillsDirectory = effectiveDefaultSkillsDirectory(null) ?? ""
  const currentDefaultSkillsDirectory = effectiveDefaultSkillsDirectory(appSettings.defaultSkillsDirectory)

  useEffect(() => {
    let active = true
    setTruthSourcesLoading(true)
    setTruthSourcesError(null)
    getTruthSources()
      .then((response) => {
        if (active) setTruthSections(response.sections)
      })
      .catch((error: unknown) => {
        if (!active) return
        setTruthSourcesError(error instanceof Error ? error.message : String(error))
      })
      .finally(() => {
        if (active) setTruthSourcesLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    getCommunityCatalogConfig()
      .then((config) => {
        if (active) setCatalogConfig(config)
      })
      .catch(() => undefined)
    return () => {
      active = false
    }
  }, [])

  async function chooseDefaultSkillsDirectory() {
    setSelectingDefaultFolder(true)
    try {
      const directory = await selectSkillDirectory(currentDefaultSkillsDirectory)
      if (directory) {
        appSettings.setDefaultSkillsDirectory(directory)
      }
    } finally {
      setSelectingDefaultFolder(false)
    }
  }

  async function openTruthSource(source: TruthSource) {
    const opened = await openLocalPath(source.path)
    if (opened) return
    if (!source.can_preview) return
    try {
      const content = await getTruthSourceContent(source.id)
      setPreview(content)
    } catch (error) {
      const description = error instanceof Error ? error.message : String(error)
      toast.error(t("general.truthSources.previewFailed"), { description })
    }
  }

  const truthSources = useMemo(
    () => truthSections.flatMap((section) => section.sources),
    [truthSections],
  )

  return (
    <div className="max-w-3xl">
      <SectionTitle
        title={t("general.title")}
        description={t("general.description")}
        trailing={<SaveStatusBadge status={appSettings.saveStatus} />}
      />

      <FieldSet>
        <FieldGroup className="gap-5">
          <Field>
            <FieldLabel htmlFor="studio-user-id">{t("general.userId.label")}</FieldLabel>
            <Input
              id="studio-user-id"
              value={appSettings.userId}
              onChange={(event) => appSettings.setUserId(event.target.value)}
              placeholder={t("general.userId.placeholder")}
              className="h-8 text-xs"
              aria-label={t("general.userId.label")}
            />
            <FieldDescription>{t("general.userId.description")}</FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor="default-skill-folder">{t("general.defaultSkillFolder.label")}</FieldLabel>
            <div className="flex min-w-0 items-center gap-2">
              <Input
                id="default-skill-folder"
                value={appSettings.defaultSkillsDirectory}
                onChange={(event) => appSettings.setDefaultSkillsDirectory(event.target.value)}
                placeholder={t("general.defaultSkillFolder.placeholder")}
                className="h-8 min-w-0 flex-1 text-xs"
                aria-label={t("general.defaultSkillFolder.label")}
                title={appSettings.defaultSkillsDirectory}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  chooseDefaultSkillsDirectory().catch(() => undefined)
                }}
                disabled={selectingDefaultFolder}
                className="h-8 shrink-0 text-xs"
              >
                <FolderOpen />
                {t("general.defaultSkillFolder.choose")}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => appSettings.setDefaultSkillsDirectory(fallbackDefaultSkillsDirectory)}
                disabled={!fallbackDefaultSkillsDirectory}
                className="size-8 shrink-0"
                aria-label={t("general.defaultSkillFolder.reset")}
              >
                <RotateCcw />
              </Button>
            </div>
            <FieldDescription>{t("general.defaultSkillFolder.description")}</FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor="gitea-host">{t("general.giteaHost.label")}</FieldLabel>
            <Input
              id="gitea-host"
              value={appSettings.giteaHost}
              onChange={(event) => appSettings.setGiteaHost(event.target.value)}
              placeholder={t("general.giteaHost.placeholder")}
              className="h-8 text-xs"
              aria-label={t("general.giteaHost.label")}
            />
            <FieldDescription>{t("general.giteaHost.description")}</FieldDescription>
          </Field>

          <Field>
            <FieldLabel
              htmlFor="remote-model-catalog-enabled"
              onClick={(event) => event.preventDefault()}
            >
              {t("general.remoteModelCatalog.label")}
            </FieldLabel>
            <div className="flex min-w-0 items-center justify-between gap-3 rounded-md bg-muted/30 p-3">
              <FieldDescription className="min-w-0 flex-1">
                {t("general.remoteModelCatalog.description")}
              </FieldDescription>
              <Switch
                id="remote-model-catalog-enabled"
                checked={appSettings.remoteModelCatalogEnabled}
                onCheckedChange={appSettings.setRemoteModelCatalogEnabled}
                aria-label={t("general.remoteModelCatalog.label")}
                className="shrink-0"
              />
            </div>
            {catalogConfig ? (
              <div className="mt-2 space-y-2 rounded-md border border-border/60 bg-muted/10 p-3">
                <p className="text-xs/relaxed text-muted-foreground">
                  {t("general.remoteModelCatalog.configNote")}
                </p>
                <CatalogConfigRow
                  label={t("general.remoteModelCatalog.manifestUrlLabel")}
                  value={catalogConfig.manifest_url}
                />
                <CatalogConfigRow
                  label={t("general.remoteModelCatalog.signingPubkeyLabel")}
                  value={catalogConfig.signing_pubkey}
                />
              </div>
            ) : null}
          </Field>

          <Field>
            <FieldLabel htmlFor="studio-language">{t("general.language.label")}</FieldLabel>
            <Select
              value={appSettings.language}
              onValueChange={(value) => {
                applyLanguageChange({
                  changeLanguage: (next) => i18n.changeLanguage(next),
                  setLanguage: appSettings.setLanguage,
                  value,
                })
              }}
            >
              <SelectTrigger
                id="studio-language"
                className="h-8 text-xs"
                aria-label={t("general.language.ariaLabel")}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">{t("general.language.english")}</SelectItem>
                <SelectItem value="zh-CN">{t("general.language.simplifiedChinese")}</SelectItem>
              </SelectContent>
            </Select>
            <FieldDescription>{t("general.language.description")}</FieldDescription>
          </Field>
        </FieldGroup>
      </FieldSet>

      <Separator className="my-8" />

      <CatalogAccordion type="multiple">
        <CatalogAccordionItem value="truth-sources">
          <CatalogAccordionTrigger>
            {t("general.truthSources.title")}
          </CatalogAccordionTrigger>
          <CatalogAccordionContent className="space-y-3 pb-5">
            <p className="text-xs text-muted-foreground">{t("general.truthSources.description")}</p>
            {truthSourcesError ? (
              <p className="text-xs text-destructive">
                {t("general.truthSources.loadFailed", { error: truthSourcesError })}
              </p>
            ) : null}
            <TruthSourceCards
              sources={truthSources}
              loading={truthSourcesLoading && truthSections.length === 0}
              onOpenSource={openTruthSource}
            />
          </CatalogAccordionContent>
        </CatalogAccordionItem>
      </CatalogAccordion>

      <Dialog open={preview !== null} onOpenChange={(open) => {
        if (!open) setPreview(null)
      }}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{t("general.truthSources.previewTitle")}</DialogTitle>
            <DialogDescription>{preview?.path}</DialogDescription>
          </DialogHeader>
          <ScrollArea className="h-[55vh] rounded-md border border-border bg-muted/20">
            <pre className="whitespace-pre-wrap break-words p-3 font-mono text-[0.6875rem] leading-relaxed text-foreground">
              {preview?.content}
            </pre>
          </ScrollArea>
          {preview?.truncated ? (
            <p className="text-xs text-muted-foreground">
              {t("general.truthSources.previewTruncated")}
            </p>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function CatalogConfigRow({ label, value }: { label: string; value: string }) {
  const { t } = useTranslation("settings")
  return (
    <div className="space-y-1">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <div className="flex min-w-0 items-center gap-1.5">
        <Input
          readOnly
          value={value}
          title={value}
          aria-label={label}
          className="h-8 overflow-x-auto whitespace-nowrap text-clip text-xs text-muted-foreground"
        />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8 shrink-0"
          aria-label={t("general.remoteModelCatalog.copy", { label })}
          onClick={() => {
            void navigator.clipboard
              .writeText(value)
              .then(() => toast.success(t("general.remoteModelCatalog.copied", { label })))
              .catch(() => toast.error(t("general.remoteModelCatalog.copyFailed")))
          }}
        >
          <Copy className="size-3.5" />
        </Button>
      </div>
    </div>
  )
}

export function TruthSourcesPanel({
  sections,
  loading,
  onOpenSource,
}: {
  sections: TruthSourceSection[]
  loading?: boolean
  onOpenSource: (source: TruthSource) => void
}) {
  const { t } = useTranslation("settings")
  const sources = sections.flatMap((section) => section.sources)

  if (loading) {
    return <p className="text-xs text-muted-foreground">{t("general.truthSources.loading")}</p>
  }

  if (sources.length === 0) {
    return <p className="text-xs text-muted-foreground">{t("general.truthSources.empty")}</p>
  }

  return <TruthSourceCards sources={sources} onOpenSource={onOpenSource} />
}

function TruthSourceCards({
  sources,
  loading,
  onOpenSource,
}: {
  sources: TruthSource[]
  loading?: boolean
  onOpenSource: (source: TruthSource) => void
}) {
  const { t } = useTranslation("settings")

  if (loading) {
    return <p className="text-xs text-muted-foreground">{t("general.truthSources.loading")}</p>
  }

  if (sources.length === 0) {
    return <p className="text-xs text-muted-foreground">{t("general.truthSources.empty")}</p>
  }

  return (
    <div className="space-y-3">
      {sources.map((source) => (
        <TruthSourceCard key={source.id} source={source} onOpenSource={onOpenSource} />
      ))}
    </div>
  )
}

function TruthSourceCard({
  source,
  onOpenSource,
}: {
  source: TruthSource
  onOpenSource: (source: TruthSource) => void
}) {
  const { t } = useTranslation("settings")
  const label = t(`general.truthSources.sources.${source.id}.label`, { defaultValue: source.label })
  const category = truthSourceCategory(source.id)
  return (
    <Card data-truth-source-id={source.id}>
      <CardHeader className="pb-2">
        <div className="min-w-0 space-y-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <div className="truncate text-sm font-semibold text-foreground">{label}</div>
            <Badge variant="secondary" className="shrink-0 text-[10px] font-normal">
              {t(truthSourceCategoryLabelKeys[category])}
            </Badge>
          </div>
          <p className="text-xs/relaxed text-muted-foreground">
            {t(`general.truthSources.sources.${source.id}.description`, {
              defaultValue: source.description,
            })}
          </p>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label htmlFor={`truth-source-path-${source.id}`}>
              {t("general.truthSources.pathLabel", { label })}
            </Label>
          </div>
          <div className={truthSourceFieldRowClassName}>
            <div className="flex flex-1 min-w-0 items-center gap-1.5">
              <Input
                id={`truth-source-path-${source.id}`}
                readOnly
                value={source.path}
                aria-label={t("general.truthSources.pathLabel", { label })}
                title={source.path}
                className={truthSourceScrollableInputClassName}
              />
            </div>
            <div className={truthSourceFieldActionClassName}>
              <Button
                type="button"
                variant="default"
                onClick={() => onOpenSource(source)}
                disabled={!source.exists}
                className={truthSourceActionButtonClassName}
              >
                <ExternalLink data-icon="inline-start" className="size-3.5 shrink-0" />
                {t("general.truthSources.open")}
              </Button>
            </div>
          </div>
        </div>
        <p className="text-xs/relaxed text-muted-foreground">{formatSourceStatus(source, t)}</p>
        <TruthSourceLogs sourceId={source.id} logs={source.logs} />
      </CardContent>
    </Card>
  )
}

function TruthSourceLogs({
  sourceId,
  logs,
}: {
  sourceId: string
  logs: RuntimeActivityLogEntry[]
}) {
  const { t } = useTranslation("settings")
  const [open, setOpen] = useState(false)
  const logScrollRootRef = useRef<HTMLDivElement>(null)
  const orderedLogs = useMemo(
    () => [...logs].sort((a, b) => timestampValue(a.recorded_at) - timestampValue(b.recorded_at)),
    [logs],
  )
  const latestLog = orderedLogs[orderedLogs.length - 1]

  useEffect(() => {
    if (!open) return
    const viewport = logScrollRootRef.current?.querySelector<HTMLElement>("[data-slot='scroll-area-viewport']")
    if (!viewport) return
    const scrollToBottom = () => {
      viewport.scrollTop = viewport.scrollHeight
    }
    scrollToBottom()
    window.setTimeout(scrollToBottom, 0)
  }, [open, orderedLogs])

  const summary = latestLog
    ? t("general.truthSources.logsSummary", {
        action: latestLog.action,
        time: formatLogTime(latestLog.recorded_at),
      })
    : t("general.truthSources.noLogs")

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mt-3 border-t border-border pt-3">
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="flex w-full items-start justify-between gap-3 rounded-sm py-1 text-left transition-colors hover:text-foreground"
          aria-label={t("general.truthSources.toggleLogs", {
            source: sourceId,
            state: open ? t("general.truthSources.hideLogs") : t("general.truthSources.showLogs"),
          })}
        >
          <span className="min-w-0">
            <span className="block text-xs font-medium text-foreground">
              {t("general.truthSources.logsTitle", { count: orderedLogs.length })}
            </span>
            <span className="mt-0.5 block text-xs/relaxed text-muted-foreground">{summary}</span>
          </span>
          <ChevronDown
            className={
              open
                ? "mt-0.5 size-4 shrink-0 rotate-0 text-muted-foreground transition-transform"
                : "mt-0.5 size-4 shrink-0 -rotate-90 text-muted-foreground transition-transform"
            }
          />
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-3">
        <div ref={logScrollRootRef}>
          <ScrollArea className="h-96 rounded-md border border-border bg-background/40">
            {orderedLogs.length === 0 ? (
              <p className="p-3 text-xs text-muted-foreground">{t("general.truthSources.noLogs")}</p>
            ) : (
              <ol className="space-y-3 p-3">
                {orderedLogs.map((log) => (
                  <RuntimeLogItem key={log.id} log={log} />
                ))}
              </ol>
            )}
          </ScrollArea>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function RuntimeLogItem({ log }: { log: RuntimeActivityLogEntry }) {
  const { t } = useTranslation("settings")
  const [detailsOpen, setDetailsOpen] = useState(false)
  const changeEntries = Object.entries(log.changes)

  return (
    <li className="text-xs/relaxed">
      <div className="flex min-w-0 flex-wrap gap-x-2 gap-y-1">
        <time className="font-mono text-muted-foreground">{formatLogTime(log.recorded_at)}</time>
        <span className="font-medium text-foreground">{log.action}</span>
      </div>
      <p className="mt-0.5 text-foreground">{log.message}</p>
      {changeEntries.length > 0 ? (
        <Collapsible open={detailsOpen} onOpenChange={setDetailsOpen} className="mt-1">
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-1 rounded-sm text-[0.6875rem] text-muted-foreground transition-colors hover:text-foreground"
              aria-label={t("general.truthSources.toggleLogDetails", {
                state: detailsOpen
                  ? t("general.truthSources.hideLogDetails")
                  : t("general.truthSources.showLogDetails"),
              })}
            >
              <ChevronDown
                className={
                  detailsOpen
                    ? "size-3.5 shrink-0 rotate-0 transition-transform"
                    : "size-3.5 shrink-0 -rotate-90 transition-transform"
                }
              />
              {t("general.truthSources.logDetailsTitle", { count: changeEntries.length })}
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <dl className="mt-1 space-y-0.5 font-mono text-[0.6875rem] text-muted-foreground">
              {changeEntries.map(([key, value]) => (
                <div key={key} className="grid grid-cols-[minmax(7rem,12rem)_minmax(0,1fr)] gap-2">
                  <dt className="min-w-0 break-words">{key}</dt>
                  <dd className="min-w-0 whitespace-pre-wrap break-words">{formatChangeValue(value)}</dd>
                </div>
              ))}
            </dl>
          </CollapsibleContent>
        </Collapsible>
      ) : null}
    </li>
  )
}

function truthSourceCategory(sourceId: string): TruthSourceCategory {
  if (sourceId === "app_settings") return "settings"
  if (sourceId === "skill_index" || sourceId === "workspaces_root" || sourceId === "default_skills_root") {
    return "workspace"
  }
  if (sourceId === "llm_credentials") return "credentials"
  if (sourceId === "llm_roles" || sourceId === "llm_role_test_results") return "roles"
  if (sourceId === "llm_health") return "health"
  if (sourceId === "llm_canonical_rules") return "modelRules"
  if (sourceId === "runtime_activity_log") return "diagnostics"
  return "runtime"
}

function formatSourceStatus(source: TruthSource, t: ReturnType<typeof useTranslation>["t"]): string {
  return t("general.truthSources.statusLine", {
    exists: source.exists ? t("general.truthSources.exists") : t("general.truthSources.missing"),
    kind: source.kind,
    size: formatSize(source.size_bytes),
    time: formatTimestamp(source.updated_at),
  })
}

function formatSize(size: number | null): string {
  if (size === null) return "-"
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function formatTimestamp(value: string | null): string {
  if (!value) return "-"
  return value.replace("T", " ").replace(/\+\d\d:\d\d$/, "")
}

function formatLogTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) return value
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date)
}

function timestampValue(value: string): number {
  const parsed = new Date(value).valueOf()
  return Number.isNaN(parsed) ? 0 : parsed
}

function formatChangeValue(value: unknown): string {
  if (Array.isArray(value)) {
    if (value.length === 0) return "-"
    return value.map((item) => formatChangeValue(item)).join("\n")
  }
  if (value === null || value === undefined) return "-"
  if (isRecord(value) && ("from" in value || "to" in value)) {
    return `${formatChangeValue(value.from)} -> ${formatChangeValue(value.to)}`
  }
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}
