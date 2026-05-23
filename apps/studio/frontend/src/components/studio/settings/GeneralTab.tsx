import { useState } from "react"
import { Check, FolderOpen, Loader2, RotateCcw, TriangleAlert } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { selectSkillDirectory } from "@/lib/tauri"
import { effectiveDefaultSkillsDirectory } from "@/utils/skill-paths"
import { SectionTitle } from "./shared"
import type { SettingsPageContentProps } from "./types"

function AppSettingsSaveStatusBadge({ status }: { status: SettingsPageContentProps["appSettings"]["saveStatus"] }) {
  if (status === "idle") return null
  if (status === "pending" || status === "saving") {
    return (
      <Badge variant="outline" className="gap-1 text-[10px] font-normal text-muted-foreground">
        <Loader2 className="size-3 animate-spin" />
        {status === "pending" ? "Pending" : "Saving"}
      </Badge>
    )
  }
  if (status === "saved") {
    return (
      <Badge variant="outline" className="gap-1 text-[10px] font-normal">
        <Check className="size-3" />
        Saved
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="gap-1 text-[10px] font-normal">
      <TriangleAlert className="size-3" />
      Save failed
    </Badge>
  )
}

export function GeneralTab({ appSettings }: Pick<SettingsPageContentProps, "appSettings">) {
  const [selectingDefaultFolder, setSelectingDefaultFolder] = useState(false)
  const fallbackDefaultSkillsDirectory = effectiveDefaultSkillsDirectory(null) ?? ""
  const currentDefaultSkillsDirectory = effectiveDefaultSkillsDirectory(appSettings.defaultSkillsDirectory)

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

  return (
    <div className="max-w-3xl">
      <SectionTitle
        title="General"
        description="Application defaults and collaboration identity. Changes auto-save."
        trailing={<AppSettingsSaveStatusBadge status={appSettings.saveStatus} />}
      />
      <FieldSet>
        <FieldGroup className="gap-5">
          <Field>
            <FieldLabel htmlFor="studio-user-id">Studio User ID</FieldLabel>
            <Input
              id="studio-user-id"
              value={appSettings.userId}
              onChange={(event) => appSettings.setUserId(event.target.value)}
              placeholder="your-username"
              className="h-8 text-xs"
              aria-label="Studio User ID"
              disabled={appSettings.isLoading}
            />
            <FieldDescription>Used as the local Git author and team owner.</FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor="default-skill-folder">Default skill folder</FieldLabel>
            <div className="flex min-w-0 items-center gap-2">
              <Input
                id="default-skill-folder"
                value={appSettings.defaultSkillsDirectory}
                onChange={(event) => appSettings.setDefaultSkillsDirectory(event.target.value)}
                placeholder="Select a folder path"
                className="h-8 min-w-0 flex-1 text-xs"
                aria-label="Default skill folder"
                disabled={appSettings.isLoading}
                title={appSettings.defaultSkillsDirectory}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void chooseDefaultSkillsDirectory()}
                disabled={appSettings.isLoading || selectingDefaultFolder}
                className="h-8 shrink-0 text-xs"
              >
                <FolderOpen />
                Choose
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => appSettings.setDefaultSkillsDirectory(fallbackDefaultSkillsDirectory)}
                disabled={appSettings.isLoading || !fallbackDefaultSkillsDirectory}
                className="size-8 shrink-0"
                aria-label="Reset default skill folder"
              >
                <RotateCcw />
              </Button>
            </div>
            <FieldDescription>New skills are created here when no folder is chosen.</FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor="gitea-host">Gitea Host</FieldLabel>
            <Input
              id="gitea-host"
              value={appSettings.giteaHost}
              onChange={(event) => appSettings.setGiteaHost(event.target.value)}
              placeholder="https://gitea.example.com"
              className="h-8 text-xs"
              aria-label="Gitea Host"
              disabled={appSettings.isLoading}
            />
            <FieldDescription>Private Gitea host used for team collaboration.</FieldDescription>
          </Field>
        </FieldGroup>
      </FieldSet>
    </div>
  )
}
