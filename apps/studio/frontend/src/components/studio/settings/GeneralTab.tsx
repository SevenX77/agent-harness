import { useState } from "react"
import { FolderOpen, RotateCcw } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { SaveStatusBadge } from "@/components/ui/save-status-badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { selectSkillDirectory } from "@/lib/tauri"
import { effectiveDefaultSkillsDirectory } from "@/utils/skill-paths"
import { SectionTitle } from "./shared"
import type { SettingsPageContentProps } from "./types"

export function GeneralTab({ appSettings }: Pick<SettingsPageContentProps, "appSettings">) {
  const { i18n, t } = useTranslation("settings")
  const [selectingDefaultFolder, setSelectingDefaultFolder] = useState(false)
  const fallbackDefaultSkillsDirectory = effectiveDefaultSkillsDirectory(null) ?? ""
  const currentDefaultSkillsDirectory = effectiveDefaultSkillsDirectory(appSettings.defaultSkillsDirectory)
  const currentLanguage = i18n.resolvedLanguage === "zh-CN" || i18n.language === "zh-CN" ? "zh-CN" : "en"

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
              disabled={appSettings.isLoading}
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
                {t("general.defaultSkillFolder.choose")}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => appSettings.setDefaultSkillsDirectory(fallbackDefaultSkillsDirectory)}
                disabled={appSettings.isLoading || !fallbackDefaultSkillsDirectory}
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
              disabled={appSettings.isLoading}
            />
            <FieldDescription>{t("general.giteaHost.description")}</FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor="studio-language">{t("general.language.label")}</FieldLabel>
            <Select
              value={currentLanguage}
              onValueChange={(value) => {
                void i18n.changeLanguage(value)
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
    </div>
  )
}
