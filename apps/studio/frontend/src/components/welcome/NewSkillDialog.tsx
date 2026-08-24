import type { FormEvent } from 'react'
import { FolderOpen, Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '../ui/button'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { normalizeSkillId } from './utils'

interface NewSkillDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  newSkillName: string
  onNewSkillNameChange: (value: string) => void
  parentDirectory: string | null
  defaultParentDirectory: string | null
  selectingParentDirectory: boolean
  onChooseParentDirectory: () => void
  newSkillError: string | null
  creating: boolean
  onSubmit: (event?: FormEvent) => void
  /** F6 entry ①: create the folder, then hand the empty skill to the wizard
   *  instead of leaving the person on a canvas of starter files. */
  onSubmitWithWizard: () => void
}

export function NewSkillDialog({
  open,
  onOpenChange,
  newSkillName,
  onNewSkillNameChange,
  parentDirectory,
  defaultParentDirectory,
  selectingParentDirectory,
  onChooseParentDirectory,
  newSkillError,
  creating,
  onSubmit,
  onSubmitWithWizard,
}: NewSkillDialogProps) {
  const { t } = useTranslation('welcome')
  const currentParentDirectory = parentDirectory ?? defaultParentDirectory ?? ''
  const nameMissing = !newSkillName.trim()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(calc(100vw-2rem),52rem)] rounded-md border border-border bg-popover p-4 shadow-xl ring-0 sm:max-w-3xl">
        <form onSubmit={(event) => void onSubmit(event)}>
          <DialogHeader>
            <DialogTitle>{t('dialog.title')}</DialogTitle>
            <DialogDescription>{t('dialog.description')}</DialogDescription>
          </DialogHeader>
          <div className="my-4 space-y-4">
            <div className="space-y-2">
              <Label htmlFor="new-skill-name">{t('dialog.nameLabel')}</Label>
              <Input
                id="new-skill-name"
                autoFocus
                value={newSkillName}
                onChange={(event) => onNewSkillNameChange(event.target.value)}
                placeholder={t('dialog.namePlaceholder')}
                aria-invalid={Boolean(newSkillError)}
                disabled={creating}
              />
              {newSkillError ? (
                <p className="max-h-28 overflow-y-auto break-words rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1.5 text-xs text-destructive">
                  {newSkillError}
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  {t('dialog.folderNameLabel')} <span className="font-mono">{normalizeSkillId(newSkillName || 'new-skill')}</span>
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label>{t('dialog.parentLabel')}</Label>
              <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                <Input
                  readOnly
                  value={currentParentDirectory}
                  placeholder={t('dialog.parentPlaceholder')}
                  className="min-w-0 font-mono text-xs"
                  aria-label={t('dialog.parentLabel')}
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={onChooseParentDirectory}
                  disabled={creating || selectingParentDirectory}
                >
                  <FolderOpen />
                  {selectingParentDirectory ? t('dialog.choosing') : t('dialog.chooseFolder')}
                </Button>
              </div>
            </div>
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline" disabled={creating}>
                {t('dialog.cancel')}
              </Button>
            </DialogClose>
            <Button
              type="button"
              variant="outline"
              onClick={onSubmitWithWizard}
              disabled={creating || nameMissing}
            >
              <Sparkles />
              {t('dialog.planTogether')}
            </Button>
            <Button type="submit" disabled={creating || nameMissing}>
              {creating ? t('dialog.creating') : t('dialog.create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
