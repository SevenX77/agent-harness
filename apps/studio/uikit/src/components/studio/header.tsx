import { ChevronDown, Play, Zap, Sun, Moon, Sparkles } from "lucide-react"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Separator } from "@/components/ui/separator"
import { useTheme } from "@/hooks/use-theme"

type Status = "draft" | "compiled" | "running"

interface HeaderProps {
  projectName: string
  status: Status
  copilotOpen: boolean
  onCopilotToggle: () => void
}

const STATUS_VARIANT: Record<
  Status,
  "default" | "secondary" | "outline"
> = {
  draft: "outline",
  compiled: "secondary",
  running: "default",
}

export function Header({
  projectName,
  status,
  copilotOpen,
  onCopilotToggle,
}: HeaderProps) {
  const { theme, toggleTheme } = useTheme()

  return (
    <header className="h-11 border-b border-border flex items-center justify-between px-3 bg-background">
      {/* Left: Project Info */}
      <div className="flex items-center gap-3">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="gap-1.5 px-2">
              <span className="text-xs font-medium">{projectName}</span>
              <ChevronDown className="text-muted-foreground" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-48">
            <DropdownMenuGroup>
              <DropdownMenuItem>Rename</DropdownMenuItem>
              <DropdownMenuItem>Duplicate</DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem>Export</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Separator orientation="vertical" className="h-4" />

        <span className="text-xs text-muted-foreground">Workspace</span>

        <Badge variant={STATUS_VARIANT[status]} className="uppercase">
          {status}
        </Badge>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-1.5">
        <Button variant="ghost" className="gap-1.5">
          <Zap />
          Predict
        </Button>

        <Button className="gap-1.5">
          <Play fill="currentColor" />
          Run
        </Button>

        <Separator orientation="vertical" className="h-4 mx-1" />

        {/* Copilot Toggle */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={onCopilotToggle}
              aria-pressed={copilotOpen}
            >
              <Sparkles />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {copilotOpen ? "Hide Copilot" : "Show Copilot"}
          </TooltipContent>
        </Tooltip>

        {/* Theme Toggle: shows the target mode you'd switch to */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon" onClick={toggleTheme}>
              {theme === "dark" ? <Sun /> : <Moon />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          </TooltipContent>
        </Tooltip>

        {/* User */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="rounded-full">
              <Avatar className="size-6">
                <AvatarImage src="https://github.com/shadcn.png" />
                <AvatarFallback>U</AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuGroup>
              <DropdownMenuItem>Profile</DropdownMenuItem>
              <DropdownMenuItem>Settings</DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem>Sign out</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
