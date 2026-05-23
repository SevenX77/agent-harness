import type { SkillSummary } from '../../api/types'
import { Badge } from '../ui/badge'
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '../ui/command'

interface SkillPaletteProps {
  open: boolean
  skills: SkillSummary[]
  selectedSkillId: string | null
  onSelect: (skillId: string) => void
  onClose: () => void
}

export function SkillPalette({
  open,
  skills,
  selectedSkillId,
  onSelect,
  onClose,
}: SkillPaletteProps) {
  if (!open) {
    return null
  }

  return (
    <CommandDialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          onClose()
        }
      }}
      title="Skill Palette"
      description="Search and switch skills."
      className="max-w-xl"
      showCloseButton
    >
      <Command>
        <CommandInput placeholder="Search skills" />
        <CommandList>
          <CommandEmpty>No skills found.</CommandEmpty>
          <CommandGroup>
            {skills.map((skill) => (
              <CommandItem
                key={skill.id}
                value={`${skill.name} ${skill.id} ${skill.description}`}
                data-checked={skill.id === selectedSkillId}
                onSelect={() => {
                  onSelect(skill.id)
                  onClose()
                }}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{skill.name}</span>
                  <span className="block truncate text-muted-foreground">{skill.description}</span>
                </span>
                {skill.id === selectedSkillId ? (
                  <Badge variant="secondary">Current</Badge>
                ) : null}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
