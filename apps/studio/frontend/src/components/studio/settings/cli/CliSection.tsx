import { useCallback, useEffect, useMemo, useState } from "react"
import { Download, Loader2, RefreshCw } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cliDependencyStatus, launchCliInstaller, type CliDependencyRow } from "@/lib/tauri"
import type { CliSessionProviderSettings, CliSessionSettings } from "@/api/types"

// 与 copilot 路由灯同一套语义 token(bg-success / bg-warning / bg-destructive /
// bg-muted),一色一义:ok=绿、outdated=黄、missing/broken=红、unknown=灰。
function lightClass(state: CliDependencyRow["state"]): string {
  if (state === "ok") return "bg-success ring-success-border"
  if (state === "outdated") return "bg-warning ring-warning-border"
  if (state === "unknown") return "bg-muted ring-foreground/20"
  return "bg-destructive ring-destructive-border"
}

// claude --effort 的合法档位(CLI --help 实测 2026-08-06);codex 的
// model_reasoning_effort 档位取 codex 文档词汇。空串 = 跟随 CLI 默认。
const CLAUDE_EFFORT_LEVELS = ["low", "medium", "high", "xhigh", "max"] as const
const CODEX_EFFORT_LEVELS = ["minimal", "low", "medium", "high"] as const
const MOIRAI_WORKER_AGENTS = ["clotho", "lachesis", "atropos"] as const

function EffortSelect({
  value,
  levels,
  placeholder,
  onChange,
  label,
}: {
  value: string
  levels: readonly string[]
  placeholder: string
  onChange: (next: string) => void
  label: string
}) {
  // Radix Select 的 item 值不允许空串;用 "default" 哨兵表示「跟随 CLI 默认」。
  return (
    <Select value={value || "default"} onValueChange={(next) => onChange(next === "default" ? "" : next)}>
      <SelectTrigger size="sm" aria-label={label} className="w-32">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="default">{placeholder}</SelectItem>
        {levels.map((level) => (
          <SelectItem key={level} value={level}>
            {level}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/**
 * Settings → Copilot →「CLI」区(设计 00_settings-ux-spec.md §3.9):
 * ① Open in CLI 依赖链 + 登录态的只读探测(owner = Tauri,分 OS);
 * ② 一键安装 = 拉起真控制台跑仓内安装脚本(含交互式 OAuth,只读流不承载);
 * ③ 会话配置(claude/codex 默认 model/effort + MoirAI worker 模型覆盖),
 *    truth 在 backend settings,经 useAppSettings 同一实例 autosave。
 */
export function CliSection({
  settings,
}: {
  settings?: { value: CliSessionSettings; onChange: (next: CliSessionSettings) => void }
}) {
  const { t } = useTranslation("settings")
  const [rows, setRows] = useState<CliDependencyRow[] | null>(null)
  const [probing, setProbing] = useState(true)
  const [desktopMissing, setDesktopMissing] = useState(false)

  const probe = useCallback(async () => {
    setProbing(true)
    try {
      const next = await cliDependencyStatus()
      if (next === null) {
        setDesktopMissing(true)
        setRows(null)
      } else {
        setDesktopMissing(false)
        setRows(next)
      }
    } finally {
      setProbing(false)
    }
  }, [])

  useEffect(() => {
    void probe()
  }, [probe])

  const needsInstall = useMemo(
    () => (rows ?? []).some((row) => row.state === "missing" || row.state === "broken" || row.state === "outdated"),
    [rows],
  )

  const handleInstall = useCallback(async () => {
    const error = await launchCliInstaller()
    if (error) {
      toast.error(t("cli.installFailed"), { description: error })
      return
    }
    toast.info(t("cli.installStarted"), { description: t("cli.installStartedDetail") })
  }, [t])

  const patchProvider = useCallback(
    (provider: "claude" | "codex", patch: Partial<CliSessionProviderSettings>) => {
      if (!settings) return
      settings.onChange({
        ...settings.value,
        [provider]: { ...settings.value[provider], ...patch },
      })
    },
    [settings],
  )

  const patchAgent = useCallback(
    (agent: string, patch: Partial<CliSessionProviderSettings>) => {
      if (!settings) return
      const current = settings.value.agents[agent] ?? { model: "", effort: "" }
      settings.onChange({
        ...settings.value,
        agents: { ...settings.value.agents, [agent]: { ...current, ...patch } },
      })
    },
    [settings],
  )

  if (desktopMissing) {
    return (
      <Empty data-cli-section-desktop-only="true">
        <EmptyHeader>
          <EmptyTitle>{t("cli.desktopOnly")}</EmptyTitle>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <div className="space-y-5" data-cli-section="true">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{t("cli.description")}</p>
        <div className="flex items-center gap-2">
          {needsInstall ? (
            <Button
              type="button"
              variant="default"
              size="sm"
              onClick={() => void handleInstall()}
              data-cli-install-button="true"
            >
              <Download data-icon="inline-start" />
              {t("cli.install")}
            </Button>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void probe()}
            disabled={probing}
            aria-label={t("cli.reprobe")}
          >
            {probing ? (
              <Loader2 data-icon="inline-start" className="animate-spin" />
            ) : (
              <RefreshCw data-icon="inline-start" />
            )}
            {t("cli.reprobe")}
          </Button>
        </div>
      </div>

      {rows === null && probing ? (
        <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          {t("cli.probing")}
        </div>
      ) : (
        <ul className="divide-y divide-border rounded-md border border-border">
          {(rows ?? []).map((row) => (
            <li key={row.id} className="flex items-center gap-3 px-3 py-2" data-cli-dependency={row.id}>
              <span
                aria-hidden="true"
                className={`size-2 shrink-0 rounded-full ring-1 ${lightClass(row.state)}`}
              />
              <span className="min-w-28 text-sm font-medium text-foreground">
                {t(`cli.deps.${row.id}`, { defaultValue: row.id })}
              </span>
              <span className="text-xs text-muted-foreground" data-cli-dependency-state={row.state}>
                {t(`cli.states.${row.state}`, { defaultValue: row.state })}
              </span>
              {row.version ? (
                <span className="truncate text-xs text-muted-foreground">{row.version}</span>
              ) : null}
              {row.detail ? (
                <span className="ml-auto truncate text-xs text-destructive" title={row.detail}>
                  {row.detail}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {settings ? (
        <div className="space-y-4" data-cli-session-config="true">
          <p className="text-sm font-medium text-foreground">{t("cli.sessionConfig.title")}</p>
          <p className="text-xs text-muted-foreground">{t("cli.sessionConfig.description")}</p>
          {(["claude", "codex"] as const).map((provider) => (
            <div key={provider} className="flex items-center gap-3" data-cli-provider-config={provider}>
              <span className="min-w-28 text-sm text-foreground">
                {t(`cli.deps.${provider}`, { defaultValue: provider })}
              </span>
              <Input
                value={settings.value[provider].model}
                placeholder={t("cli.sessionConfig.modelPlaceholder")}
                aria-label={t("cli.sessionConfig.modelAria", { provider })}
                className="h-8 max-w-64 text-sm"
                onChange={(event) => patchProvider(provider, { model: event.target.value })}
              />
              <EffortSelect
                value={settings.value[provider].effort}
                levels={provider === "claude" ? CLAUDE_EFFORT_LEVELS : CODEX_EFFORT_LEVELS}
                placeholder={t("cli.sessionConfig.effortDefault")}
                label={t("cli.sessionConfig.effortAria", { provider })}
                onChange={(effort) => patchProvider(provider, { effort })}
              />
            </div>
          ))}
          <p className="text-xs text-muted-foreground">{t("cli.sessionConfig.agentsHint")}</p>
          {MOIRAI_WORKER_AGENTS.map((agent) => (
            <div key={agent} className="flex items-center gap-3" data-cli-agent-config={agent}>
              <span className="min-w-28 text-sm text-foreground">{agent}</span>
              <Input
                value={settings.value.agents[agent]?.model ?? ""}
                placeholder={t("cli.sessionConfig.agentModelPlaceholder")}
                aria-label={t("cli.sessionConfig.agentModelAria", { agent })}
                className="h-8 max-w-64 text-sm"
                onChange={(event) => patchAgent(agent, { model: event.target.value })}
              />
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
