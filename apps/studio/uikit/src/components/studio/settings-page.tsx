import { useState } from "react"
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
import { useTheme } from "@/hooks/use-theme"

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
    <div className="size-full bg-background flex flex-col">
      <div className="h-11 flex items-center justify-between gap-2 pl-4 pr-2 border-b border-border shrink-0">
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

      <div className="flex-1 flex min-h-0">
        <nav className="w-56 border-r border-border bg-sidebar/40 shrink-0 py-4 px-2">
          {SECTIONS.map((s) => {
            const isActive = active === s.id
            return (
              <button
                key={s.id}
                onClick={() => setActive(s.id)}
                className={cn(
                  "w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-sm text-xs transition-colors",
                  isActive
                    ? "bg-sidebar-accent text-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
                )}
              >
                <s.icon className="size-3.5" strokeWidth={1.75} />
                {s.label}
              </button>
            )
          })}
        </nav>

        <ScrollArea className="flex-1">
          <div className="max-w-2xl px-10 py-8">
            {active === "account" && <AccountSection />}
            {active === "general" && <GeneralSection />}
            {active === "appearance" && <AppearanceSection />}
            {active === "keybindings" && <KeybindingsSection />}
            {active === "notifications" && <NotificationsSection />}
            {active === "integrations" && <IntegrationsSection />}
            {active === "privacy" && <PrivacySection />}
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
      {description && (
        <p className="text-xs text-muted-foreground mt-1">{description}</p>
      )}
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
  control: React.ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-6 py-3">
      <div className="flex-1 min-w-0">
        <Label className="text-xs font-medium text-foreground">{label}</Label>
        {description && (
          <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">
            {description}
          </p>
        )}
      </div>
      <div className="shrink-0">{control}</div>
    </div>
  )
}

function AccountSection() {
  return (
    <div>
      <SectionTitle title="Account" description="Manage your profile and session." />

      <div className="flex items-center gap-4 p-4 rounded-md border border-border bg-card mb-6">
        <Avatar className="size-12">
          <AvatarImage src="https://github.com/shadcn.png" />
          <AvatarFallback>U</AvatarFallback>
        </Avatar>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-foreground">shadcn</div>
          <div className="text-xs text-muted-foreground truncate">
            shadcn@example.com
          </div>
        </div>
        <Button variant="outline" size="sm">
          Manage
        </Button>
      </div>

      <Separator className="my-4" />

      <SettingRow
        label="Display name"
        control={<Input defaultValue="shadcn" className="w-56 h-8 text-xs" />}
      />
      <SettingRow
        label="Email"
        control={
          <Input
            defaultValue="shadcn@example.com"
            className="w-56 h-8 text-xs"
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
  const { theme, setTheme } = useTheme()
  const themeOptions: Array<{ id: "light" | "dark"; label: string; icon: typeof Sun }> = [
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
          <div className="inline-flex items-center gap-0.5 bg-muted rounded-md p-0.5">
            {themeOptions.map((opt) => (
              <button
                key={opt.id}
                onClick={() => setTheme(opt.id)}
                className={cn(
                  "flex items-center gap-1.5 px-2.5 py-1 rounded-sm text-xs transition-colors",
                  theme === opt.id
                    ? "bg-card text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <opt.icon className="size-3.5" strokeWidth={1.75} />
                {opt.label}
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
    { action: "Toggle Copilot", keys: "⌘ K" },
    { action: "Run skill", keys: "⌘ ↵" },
  ]

  return (
    <div>
      <SectionTitle title="Keybindings" description="Default keyboard shortcuts." />
      <div className="space-y-px">
        {bindings.map((b) => (
          <div
            key={b.action}
            className="flex items-center justify-between py-2 px-2 rounded-sm hover:bg-muted/40"
          >
            <span className="text-xs text-foreground">{b.action}</span>
            <kbd className="text-[11px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
              {b.keys}
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
  return (
    <div>
      <SectionTitle title="Integrations" description="Connect external services." />
      <SettingRow
        label="OpenAI"
        description="Connect your OpenAI account for LLM calls."
        control={
          <Button variant="outline" size="sm">
            Connect
          </Button>
        }
      />
      <SettingRow
        label="Anthropic"
        description="Connect Anthropic for Claude models."
        control={
          <Button variant="outline" size="sm">
            Connect
          </Button>
        }
      />
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
