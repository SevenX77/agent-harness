import { useCallback, useEffect, useState } from "react"
import { Loader2, RefreshCw } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { cliDependencyStatus, type CliDependencyRow } from "@/lib/tauri"

// 与 copilot 路由灯同一套语义 token(bg-success / bg-warning / bg-destructive /
// bg-muted),一色一义:ok=绿、outdated=黄、missing/broken=红、unknown=灰。
function lightClass(state: CliDependencyRow["state"]): string {
  if (state === "ok") return "bg-success ring-success-border"
  if (state === "outdated") return "bg-warning ring-warning-border"
  if (state === "unknown") return "bg-muted ring-foreground/20"
  return "bg-destructive ring-destructive-border"
}

/**
 * Settings → Copilot →「CLI」区(提案 2026-08-06,PR-1 状态面板):
 * Open in CLI 依赖链(WSL/ah/tmux/claude/codex)+ 登录态的只读探测。
 * 探测归 Tauri(桌面本机事实);进区冷加载一次 + 显式「重新检测」。
 */
export function CliSection() {
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
    <div className="space-y-3" data-cli-section="true">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{t("cli.description")}</p>
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
    </div>
  )
}
