import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { SectionTitle, SettingRow } from "./shared"
import type { SettingsPageContentProps } from "./types"

export function GeneralTab({ appSettings }: Pick<SettingsPageContentProps, "appSettings">) {
  return (
    <div>
      <SectionTitle title="General" description="Application defaults and collaboration identity." />
      <SettingRow
        label="Studio User ID"
        description="Used as the local Git author and team owner."
        control={
          <div className="flex items-center gap-2">
            <Input
              value={appSettings.userId}
              onChange={(event) => appSettings.setUserId(event.target.value)}
              placeholder="your-username"
              className="h-8 w-56 text-xs"
              aria-label="Studio User ID"
            />
            <Button type="button" size="sm" onClick={() => void appSettings.save()} disabled={appSettings.isLoading} className="h-7 text-xs">
              Save
            </Button>
          </div>
        }
      />
      <SettingRow
        label="Gitea Host"
        description="Private Gitea host used for team collaboration."
        control={
          <div className="flex items-center gap-2">
            <Input
              value={appSettings.giteaHost}
              onChange={(event) => appSettings.setGiteaHost(event.target.value)}
              placeholder="https://gitea.example.com"
              className="h-8 w-56 text-xs"
              aria-label="Gitea Host"
            />
            <Button type="button" size="sm" onClick={() => void appSettings.save()} disabled={appSettings.isLoading} className="h-7 text-xs">
              Save
            </Button>
          </div>
        }
      />
    </div>
  )
}
