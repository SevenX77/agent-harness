import { useEffect, useState, type FormEvent, type ReactNode } from "react"
import {
  Bell,
  CircleUser,
  Cog,
  Keyboard,
  Monitor,
  Moon,
  Plug,
  ShieldCheck,
  Sun,
  X,
} from "lucide-react"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"
import { setTheme, useThemeValue, type Theme } from "@/store/themeStore"
import { getCopilotCredentials, updateCopilotCredentials } from "../../api/copilot"
import type { CopilotBackend, CopilotCredentials } from "../../types/copilot"

const COPILOT_BACKENDS: Array<{ id: CopilotBackend; label: string; disabled?: boolean }> = [
  { id: "claude", label: "Claude" },
  { id: "deepseek", label: "DeepSeek" },
  { id: "gemini", label: "Gemini", disabled: true },
  { id: "openai", label: "OpenAI", disabled: true },
]

type SectionId =
  | "account"
  | "general"
  | "appearance"
  | "keybindings"
  | "notifications"
  | "integrations"
  | "privacy"

interface SectionDef {
  id: SectionId
  label: string
  icon: typeof Cog
}

const SECTIONS: SectionDef[] = [
  { id: "account", label: "Account", icon: CircleUser },
  { id: "general", label: "General", icon: Cog },
  { id: "appearance", label: "Appearance", icon: Monitor },
  { id: "keybindings", label: "Keybindings", icon: Keyboard },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "integrations", label: "Integrations", icon: Plug },
  { id: "privacy", label: "Privacy", icon: ShieldCheck },
]

interface SettingsPageProps {
  onClose: () => void
}

export function SettingsPage({ onClose }: SettingsPageProps) {
  const [active, setActive] = useState<SectionId>("account")

  return (
    <div className="flex size-full flex-col bg-background">
      <div className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-border pl-4 pr-2">
        <span className="text-sm font-semibold text-foreground">Settings</span>
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          aria-label="Close settings"
          className="size-7"
        >
          <X className="size-4" />
        </Button>
      </div>

      <div className="flex min-h-0 flex-1">
        <nav className="w-56 shrink-0 border-r border-border bg-sidebar/40 px-2 py-4">
          {SECTIONS.map((section) => {
            const isActive = active === section.id
            return (
              <button
                key={section.id}
                type="button"
                onClick={() => setActive(section.id)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-sm px-2.5 py-1.5 text-xs transition-colors",
                  isActive
                    ? "bg-sidebar-accent text-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
                )}
              >
                <section.icon className="size-3.5" strokeWidth={1.75} />
                {section.label}
              </button>
            )
          })}
        </nav>

        <ScrollArea className="flex-1">
          <div className="max-w-2xl px-10 py-8">
            {active === "account" ? <AccountSection /> : null}
            {active === "general" ? <GeneralSection /> : null}
            {active === "appearance" ? <AppearanceSection /> : null}
            {active === "keybindings" ? <KeybindingsSection /> : null}
            {active === "notifications" ? <NotificationsSection /> : null}
            {active === "integrations" ? <IntegrationsSection /> : null}
            {active === "privacy" ? <PrivacySection /> : null}
          </div>
        </ScrollArea>
      </div>
    </div>
  )
}

function SectionTitle({ title, description }: { title: string; description?: string }) {
  return (
    <div className="mb-6">
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      {description ? (
        <p className="mt-1 text-xs text-muted-foreground">{description}</p>
      ) : null}
    </div>
  )
}

function SettingRow({
  label,
  description,
  control,
}: {
  label: string
  description?: string
  control: ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-6 py-3">
      <div className="min-w-0 flex-1">
        <Label className="text-xs font-medium text-foreground">{label}</Label>
        {description ? (
          <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">
            {description}
          </p>
        ) : null}
      </div>
      <div className="shrink-0">{control}</div>
    </div>
  )
}

function AccountSection() {
  return (
    <div>
      <SectionTitle title="Account" description="Manage your profile and session." />

      <div className="mb-6 flex items-center gap-4 rounded-md border border-border bg-card p-4">
        <Avatar className="size-12">
          <AvatarImage src="https://github.com/shadcn.png" />
          <AvatarFallback>U</AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-foreground">Studio User</div>
          <div className="truncate text-xs text-muted-foreground">
            OAuth session
          </div>
        </div>
        <Button variant="outline" size="sm">
          Manage
        </Button>
      </div>

      <Separator className="my-4" />

      <SettingRow
        label="Display name"
        control={<Input defaultValue="Studio User" className="h-8 w-56 text-xs" />}
      />
      <SettingRow
        label="Email"
        control={
          <Input
            defaultValue="user@example.com"
            className="h-8 w-56 text-xs"
          />
        }
      />

      <Separator className="my-4" />

      <SettingRow
        label="Sign out"
        description="Sign out from this device. You can sign back in any time."
        control={
          <Button variant="outline" size="sm">
            Sign out
          </Button>
        }
      />
    </div>
  )
}

function GeneralSection() {
  return (
    <div>
      <SectionTitle title="General" description="Application defaults." />
      <SettingRow
        label="Auto-save"
        description="Save changes as you type."
        control={<Switch defaultChecked />}
      />
      <SettingRow
        label="Confirm before run"
        description="Prompt for confirmation when executing a skill."
        control={<Switch />}
      />
      <SettingRow
        label="Telemetry"
        description="Help improve GSkill by sharing anonymous usage data."
        control={<Switch defaultChecked />}
      />
    </div>
  )
}

function AppearanceSection() {
  const theme = useThemeValue()
  const themeOptions: Array<{ id: Theme; label: string; icon: typeof Sun }> = [
    { id: "light", label: "Light", icon: Sun },
    { id: "dark", label: "Dark", icon: Moon },
  ]

  return (
    <div>
      <SectionTitle title="Appearance" description="Theme and visual preferences." />

      <SettingRow
        label="Theme"
        description="Switch between light and dark themes."
        control={
          <div className="inline-flex items-center gap-0.5 rounded-md bg-muted p-0.5">
            {themeOptions.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => setTheme(option.id)}
                className={cn(
                  "flex items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs transition-colors",
                  theme === option.id
                    ? "bg-card text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <option.icon className="size-3.5" strokeWidth={1.75} />
                {option.label}
              </button>
            ))}
          </div>
        }
      />

      <SettingRow
        label="Compact mode"
        description="Reduce spacing throughout the interface."
        control={<Switch />}
      />
    </div>
  )
}

function KeybindingsSection() {
  const bindings: Array<{ action: string; keys: string }> = [
    { action: "Toggle Assets panel", keys: "1" },
    { action: "Toggle Input panel", keys: "2" },
    { action: "Toggle Timeline panel", keys: "3" },
    { action: "Toggle Properties panel", keys: "4" },
    { action: "Toggle Local History panel", keys: "5" },
    { action: "Toggle Copilot", keys: "Cmd K" },
    { action: "Run skill", keys: "Cmd Enter" },
  ]

  return (
    <div>
      <SectionTitle title="Keybindings" description="Default keyboard shortcuts." />
      <div className="space-y-px">
        {bindings.map((binding) => (
          <div
            key={binding.action}
            className="flex items-center justify-between rounded-sm px-2 py-2 hover:bg-muted/40"
          >
            <span className="text-xs text-foreground">{binding.action}</span>
            <kbd className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
              {binding.keys}
            </kbd>
          </div>
        ))}
      </div>
    </div>
  )
}

function NotificationsSection() {
  return (
    <div>
      <SectionTitle title="Notifications" description="Choose what to be notified about." />
      <SettingRow
        label="Run completion"
        description="Notify when a skill run completes."
        control={<Switch defaultChecked />}
      />
      <SettingRow
        label="Compile errors"
        control={<Switch defaultChecked />}
      />
      <SettingRow label="Product updates" control={<Switch />} />
    </div>
  )
}

function IntegrationsSection() {
  const [status, setStatus] = useState<CopilotCredentials | null>(null)
  const [activeBackend, setActiveBackend] = useState<CopilotBackend>("claude")
  const [apiKey, setApiKey] = useState("")
  const [message, setMessage] = useState("")

  useEffect(() => {
    let cancelled = false
    getCopilotCredentials()
      .then((credentials) => {
        if (cancelled) return
        setStatus(credentials)
        setActiveBackend(credentials.active_backend)
      })
      .catch(() => {
        if (!cancelled) setMessage("Credentials status unavailable.")
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage("Saving…")
    const credentials = await updateCopilotCredentials(activeBackend, apiKey || undefined, true)
    setStatus(credentials)
    setApiKey("")
    setMessage("Credentials saved through backend.")
  }

  return (
    <div>
      <SectionTitle title="Integrations" description="Connect external services." />
      <SettingRow
        label="Provider OAuth"
        description="Manage connected model providers."
        control={
          <Button variant="outline" size="sm">
            Connect
          </Button>
        }
      />
      <Separator className="my-4" />
      <SectionTitle
        title="Copilot backend"
        description="API keys are sent to the Python backend for storage. The frontend does not write credential files."
      />
      <form onSubmit={handleSubmit} className="space-y-3">
        <SettingRow
          label="Backend"
          control={
            <select
              value={activeBackend}
              onChange={(event) => setActiveBackend(event.target.value as CopilotBackend)}
              className="h-8 w-56 rounded-md border border-border bg-background px-2 text-xs"
            >
              {COPILOT_BACKENDS.map((backend) => (
                <option key={backend.id} value={backend.id} disabled={backend.disabled}>
                  {backend.label}
                  {backend.disabled
                    ? " (V1.5)"
                    : status?.backends?.[backend.id]?.has_key
                    ? " (configured)"
                    : ""}
                </option>
              ))}
            </select>
          }
        />
        <SettingRow
          label="API key"
          description={message || "Paste a key to update"}
          control={
            <Input
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="Paste a key to update"
              className="h-8 w-56 text-xs"
            />
          }
        />
        <div className="flex justify-end">
          <Button type="submit" size="sm">
            Save
          </Button>
        </div>
      </form>
    </div>
  )
}

function PrivacySection() {
  return (
    <div>
      <SectionTitle title="Privacy" description="Control how your data is handled." />
      <SettingRow
        label="Save run history"
        description="Persist run traces locally."
        control={<Switch defaultChecked />}
      />
      <SettingRow
        label="Share crash reports"
        control={<Switch defaultChecked />}
      />
    </div>
  )
}
