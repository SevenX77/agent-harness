import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from '../ui/command'
import { hotkeyLabel } from '../../utils/hotkeys'

export interface CommandAction {
  id: string
  label: string
  description: string
  hotkey?: string
  disabled?: boolean
  run: () => void
}

interface CommandPaletteProps {
  open: boolean
  actions: CommandAction[]
  onClose: () => void
}

export function CommandPalette({ open, actions, onClose }: CommandPaletteProps) {
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
      title="Command Palette"
      description="Search for a command to run."
      className="max-w-2xl"
      showCloseButton
    >
      <Command>
        <CommandInput placeholder="Search commands" />
        <CommandList>
          <CommandEmpty>No commands found.</CommandEmpty>
          <CommandGroup>
            {actions.map((action) => (
              <CommandItem
                key={action.id}
                value={`${action.label} ${action.description}`}
                disabled={action.disabled}
                onSelect={() => {
                  if (action.disabled) {
                    return
                  }
                  action.run()
                  onClose()
                }}
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">{action.label}</span>
                  <span className="block truncate text-muted-foreground">{action.description}</span>
                </span>
                {action.hotkey ? (
                  <CommandShortcut>{hotkeyLabel(action.hotkey)}</CommandShortcut>
                ) : null}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
