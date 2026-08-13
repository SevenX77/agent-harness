import { useCallback, useEffect, useMemo, useState } from "react"
import { Download, KeyRound, Loader2, PackageCheck, RefreshCw } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  cliDependencyStatus,
  deployVendoredAh,
  launchCliInstaller,
  launchCliLogin,
  launchCliUpdate,
  type CliDependencyRow,
} from "@/lib/tauri"
import type { CliSessionProviderSettings, CliSessionSettings } from "@/api/types"

// 与 copilot 路由灯同一套语义 token(bg-success / bg-warning / bg-destructive /
// bg-muted),一色一义:ok=绿、outdated=黄、missing/broken=红、unknown=灰。
function lightClass(state: CliDependencyRow["state"]): string {
  if (state === "ok") return "bg-success ring-success-border"
  if (state === "outdated") return "bg-warning ring-warning-border"
  if (state === "unknown") return "bg-muted ring-foreground/20"
  return "bg-destructive ring-destructive-border"
}

// effort/模型档位与目录(修订 2026-08-12,证据与决策:
// docs/design/2026-08-12-cli-settings-revision.md)。空串 = 跟随 CLI 默认。
// claude effort:`claude --help` 实测(2026-08-06,2026-08-12 复核仍准)。
// codex effort:0.147.0 TUI 五档 Light/Medium/High/Extra High/Ultra 的持久化词表
// (config.toml 实测 Extra High → "xhigh";二进制 strings 含 light/xhigh/ultra)。
const CLAUDE_EFFORT_LEVELS = ["low", "medium", "high", "xhigh", "max"] as const
const CODEX_EFFORT_LEVELS = ["light", "medium", "high", "xhigh", "ultra"] as const
// 模型目录 = UI 选择目录,不是 gateway 凭据/route 真相。claude 用官方别名
// (--help 原文举例 'fable'/'opus'/'sonnet';别名指向 latest,不随小版本过期);
// codex 用 0.147.0 二进制里的当前 gpt-5.6 家族。
const CLAUDE_MODEL_CHOICES = ["fable", "opus", "sonnet", "haiku"] as const
const CODEX_MODEL_CHOICES = [
  "gpt-5.6",
  "gpt-5.6-sol",
  "gpt-5.6-luna",
  "gpt-5.6-terra",
  "gpt-5.6-pro",
] as const
const MOIRAI_WORKER_AGENTS = ["clotho", "lachesis", "atropos"] as const

function DefaultChoiceSelect({
  value,
  choices,
  placeholder,
  onChange,
  label,
  className,
}: {
  value: string
  choices: readonly string[]
  placeholder: string
  onChange: (next: string) => void
  label: string
  className: string
}) {
  // Radix Select 的 item 值不允许空串;用 "default" 哨兵表示「跟随默认」。
  return (
    <Select value={value || "default"} onValueChange={(next) => onChange(next === "default" ? "" : next)}>
      <SelectTrigger size="sm" aria-label={label} className={className}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="default">{placeholder}</SelectItem>
        {choices.map((choice) => (
          <SelectItem key={choice} value={choice}>
            {choice}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

type CliRowAction =
  | { kind: "update" | "login"; provider: "claude" | "codex" }
  | { kind: "deploy" }

// 行内动作按钮判定表(修订 2026-08-12):CLI 行过时 → 更新(CLI 自带 update 命令);
// 登录行缺失/损坏 → 登录;ah 行缺失/过时 → 部署(ah 随 app 打包,决议
// docs/design/2026-08-12-ah-vendored-auto-deploy.md——它不再是用户去装的外部依赖)。
function cliRowAction(row: CliDependencyRow): CliRowAction | null {
  if (row.id === "ah" && (row.state === "missing" || row.state === "outdated")) {
    return { kind: "deploy" }
  }
  if ((row.id === "claude" || row.id === "codex") && row.state === "outdated") {
    return { kind: "update", provider: row.id }
  }
  if (row.state !== "missing" && row.state !== "broken") return null
  if (row.id === "claude_auth") return { kind: "login", provider: "claude" }
  if (row.id === "codex_auth") return { kind: "login", provider: "codex" }
  return null
}

/**
 * Settings → Copilot →「CLI」区(设计 00_settings-ux-spec.md §3.9,修订 2026-08-12):
 * ① Open in CLI 依赖链 + 登录态 + 最新版检查的只读探测(owner = Tauri,分 OS);
 * ② 一键安装 = 拉起真控制台跑仓内安装脚本;行内「更新/登录」= 拉起真控制台跑
 *    对应 CLI 自己的 update/login 命令(交互式 OAuth,只读流不承载);
 * ③ 会话配置(claude/codex 默认 model/effort + MoirAI worker model/effort 覆盖,
 *    全部下拉选择),truth 在 backend settings,经 useAppSettings 同一实例 autosave。
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

  const handleRowAction = useCallback(
    async (action: CliRowAction) => {
      // 部署是无声后台动作(不开控制台),完成即整体重新探测——显式用户命令,
      // 属 SSOT 读取原则允许的 revalidation 触发。
      if (action.kind === "deploy") {
        const result = await deployVendoredAh()
        if ("error" in result) {
          toast.error(t("cli.actionFailed"), { description: result.error })
          return
        }
        toast.success(t("cli.deployDone"), { description: result.row.version ?? undefined })
        void probe()
        return
      }
      const error =
        action.kind === "update"
          ? await launchCliUpdate(action.provider)
          : await launchCliLogin(action.provider)
      if (error) {
        toast.error(t("cli.actionFailed"), { description: error })
        return
      }
      toast.info(t(action.kind === "update" ? "cli.updateStarted" : "cli.loginStarted"), {
        description: t("cli.actionStartedDetail"),
      })
    },
    [t, probe],
  )

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
          {(rows ?? []).map((row) => {
            const action = cliRowAction(row)
            return (
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
                <span className="ml-auto flex shrink-0 items-center gap-2">
                  {row.detail ? (
                    <span
                      className={`max-w-80 truncate text-xs ${row.state === "outdated" ? "text-warning" : "text-destructive"}`}
                      title={row.detail}
                    >
                      {row.detail}
                    </span>
                  ) : null}
                  {action ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      data-cli-row-action={action.kind}
                      onClick={() => void handleRowAction(action)}
                    >
                      {action.kind === "deploy" ? (
                        <PackageCheck data-icon="inline-start" />
                      ) : action.kind === "update" ? (
                        <Download data-icon="inline-start" />
                      ) : (
                        <KeyRound data-icon="inline-start" />
                      )}
                      {t(
                        action.kind === "deploy"
                          ? "cli.deploy"
                          : action.kind === "update"
                            ? "cli.update"
                            : "cli.login",
                      )}
                    </Button>
                  ) : null}
                </span>
              </li>
            )
          })}
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
              <DefaultChoiceSelect
                value={settings.value[provider].model}
                choices={provider === "claude" ? CLAUDE_MODEL_CHOICES : CODEX_MODEL_CHOICES}
                placeholder={t("cli.sessionConfig.modelPlaceholder")}
                label={t("cli.sessionConfig.modelAria", { provider })}
                className="w-56"
                onChange={(model) => patchProvider(provider, { model })}
              />
              <DefaultChoiceSelect
                value={settings.value[provider].effort}
                choices={provider === "claude" ? CLAUDE_EFFORT_LEVELS : CODEX_EFFORT_LEVELS}
                placeholder={t("cli.sessionConfig.effortDefault")}
                label={t("cli.sessionConfig.effortAria", { provider })}
                className="w-32"
                onChange={(effort) => patchProvider(provider, { effort })}
              />
            </div>
          ))}
          <p className="text-xs text-muted-foreground">{t("cli.sessionConfig.agentsHint")}</p>
          {MOIRAI_WORKER_AGENTS.map((agent) => (
            <div key={agent} className="flex items-center gap-3" data-cli-agent-config={agent}>
              <span className="min-w-28 text-sm text-foreground">{agent}</span>
              <DefaultChoiceSelect
                value={settings.value.agents[agent]?.model ?? ""}
                choices={CLAUDE_MODEL_CHOICES}
                placeholder={t("cli.sessionConfig.agentDefaultPlaceholder")}
                label={t("cli.sessionConfig.agentModelAria", { agent })}
                className="w-56"
                onChange={(model) => patchAgent(agent, { model })}
              />
              <DefaultChoiceSelect
                value={settings.value.agents[agent]?.effort ?? ""}
                choices={CLAUDE_EFFORT_LEVELS}
                placeholder={t("cli.sessionConfig.agentDefaultPlaceholder")}
                label={t("cli.sessionConfig.agentEffortAria", { agent })}
                className="w-32"
                onChange={(effort) => patchAgent(agent, { effort })}
              />
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
