import { Copy, FolderOpen } from "lucide-react"
import type { ReactElement } from "react"
import { toast } from "sonner"
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from "@/components/ui/context-menu"
import { revealInFileManager } from "@/lib/tauri"

export function absoluteAssetPath(root?: string | null, relativePath?: string | null): string | null {
  const trimmedRoot = root?.trim()
  if (!trimmedRoot) return null

  const normalizedRelative = relativePath?.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "") ?? ""
  if (!normalizedRelative) return trimmedRoot

  const rootWithoutTrailingSlash = trimmedRoot.replace(/[\\/]+$/, "")
  const separator = trimmedRoot.includes("\\") ? "\\" : "/"
  return `${rootWithoutTrailingSlash}${separator}${normalizedRelative.split("/").join(separator)}`
}

function fileManagerActionLabel(): string {
  if (typeof navigator === "undefined") return "Open in File Manager"

  const platform = `${navigator.platform} ${navigator.userAgent}`.toLowerCase()
  if (platform.includes("mac")) return "Reveal in Finder"
  if (platform.includes("win")) return "Show in File Explorer"
  return "Open in File Manager"
}

async function copyAbsolutePath(path: string): Promise<void> {
  const targetPath = path.trim()
  if (!targetPath) return

  if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
    toast.error("Clipboard unavailable", { description: targetPath })
    return
  }

  try {
    await navigator.clipboard.writeText(targetPath)
    toast.success("Path copied", { description: targetPath })
  } catch {
    toast.error("Could not copy path", { description: targetPath })
  }
}

export function AssetPathContextMenu({
  absolutePath,
  children,
}: {
  absolutePath?: string | null
  children: ReactElement
}) {
  const targetPath = absolutePath?.trim()
  if (!targetPath) return children

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent className="w-52">
        <ContextMenuItem onSelect={() => { void revealInFileManager(targetPath) }}>
          <FolderOpen />
          {fileManagerActionLabel()}
        </ContextMenuItem>
        <ContextMenuItem onSelect={() => { void copyAbsolutePath(targetPath) }}>
          <Copy />
          Copy path
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  )
}
