import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { GraphCanvas, type SkillGraphNodeData } from "@/components/GraphCanvas"
import { CopilotPanel } from "@/components/copilot/copilot-panel"
import { useCopilotContext } from "@/hooks/useCopilotContext"
import { readLintStatus } from "@/hooks/useDebouncedLint"
import { useSkills } from "@/hooks/useSkills"
import { WelcomePage } from "@/components/welcome/WelcomePage"
import { compileSkill, getSkillDetail, wsUrl } from "@/api/client"
import type { CompileError } from "@/api/types"
import { sha256Hex } from "@/lib/hash"
import { CenterActionBar, type SkillBuildStage } from "./center-action-bar"
import { ConflictDialog } from "./ConflictDialog"
import { Header } from "./Header"
import { Panels } from "./Panels"
import { SettingsPage } from "./SettingsPage"
import { SplitEditor } from "./SplitEditor"
import { Toolbar, type PanelKind } from "./Toolbar"
import type { FileMeta } from "./file-types"
import {
  WorkspaceProvider,
  type EditorSide,
  type OpenFile,
  type SaveConflict,
  type WorkspaceContextValue,
} from "./WorkspaceContext"

interface WorkspaceProps {
  skillId: string | null
  onSelectSkill: (skillId: string) => void
  onCloseSkill: () => void
}

export function Workspace({ skillId, onSelectSkill, onCloseSkill }: WorkspaceProps) {
  const [navStack, setNavStack] = useState<string[]>(() => (skillId ? [skillId] : []))
  const [activePanel, setActivePanel] = useState<PanelKind | null>(skillId ? "assets" : null)
  const [copilotOpen, setCopilotOpen] = useState(Boolean(skillId))
  const currentSkillId = navStack.at(-1) ?? null

  useEffect(() => {
    if (skillId === null) {
      setNavStack([])
      setActivePanel(null)
      setCopilotOpen(false)
    } else {
      setNavStack([skillId])
      setActivePanel("assets")
      setCopilotOpen(true)
    }
  }, [skillId])
  const [activeFileDetails, setActiveFileDetails] = useState<Partial<Record<EditorSide, OpenFile>>>({})
  const [splitMode, setSplitMode] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<{ id: string; data: SkillGraphNodeData } | null>(null)
  const [inFlight, setInFlight] = useState<Partial<Record<EditorSide, boolean>>>({})
  const inFlightRef = useRef<Partial<Record<EditorSide, boolean>>>({})
  const [conflict, setConflict] = useState<SaveConflict | null>(null)
  const { skillDetail, skillDetailError, mutateSkillDetail } = useSkills(currentSkillId)
  const isLoading = useMemo(() => Boolean(currentSkillId && !skillDetail && !skillDetailError), [skillDetail, skillDetailError, currentSkillId])
  const [compileStages, setCompileStages] = useState<Record<string, SkillBuildStage>>({})
  const [compileErrors, setCompileErrors] = useState<Record<string, CompileError[]>>({})

  useCopilotContext({
    skillId: currentSkillId,
    view: "Edit",
    context: {
      selected_node_id: selectedNodeId,
      selected_node: selectedNode
        ? {
            id: selectedNode.id,
            label: selectedNode.data.label,
            status: selectedNode.data.status,
            summary: typeof selectedNode.data.summary === "string" ? selectedNode.data.summary : null,
          }
        : null,
      lint_status: currentSkillId ? readLintStatus(currentSkillId) : "idle",
    },
  })

  useEffect(() => {
    inFlightRef.current = inFlight
  }, [inFlight])

  const handleNodeSelect = (node: { id: string; data: SkillGraphNodeData }) => {
    setSelectedNodeId(node.id)
    setSelectedNode(node)
  }

  const toOpenFile = useCallback(async (fileOrPath: FileMeta | string): Promise<OpenFile | null> => {
    if (!currentSkillId) return null
    const currentFiles = skillDetail?.files ?? {}
    const rawPath = typeof fileOrPath === "string" ? fileOrPath : fileOrPath.path
    const prefix = `${currentSkillId}/`
    const path = rawPath.startsWith(prefix) ? rawPath.slice(prefix.length) : rawPath
    const content = typeof fileOrPath === "string" ? currentFiles[path] ?? "" : fileOrPath.content
    const language = typeof fileOrPath === "string" ? languageForPath(path) : fileOrPath.language
    return {
      path,
      language,
      content,
      hash: await sha256Hex(content),
      skillId: currentSkillId,
    }
  }, [currentSkillId, skillDetail?.files])

  const handleFileOpen = useCallback((fileOrPath: FileMeta | string, side?: EditorSide) => {
    setSettingsOpen(false)
    void toOpenFile(fileOrPath).then((file) => {
      if (!file) return
      setActiveFileDetails((current) => {
        const targetSide = side ?? (splitMode && current.left ? "right" : "left")
        return { ...current, [targetSide]: file }
      })
    })
  }, [splitMode, toOpenFile])

  const closeFile = useCallback((side: EditorSide) => {
    setActiveFileDetails((current) => {
      const remainingSide: EditorSide = side === "left" ? "right" : "left"
      const remaining = current[remainingSide]
      setSplitMode(false)
      return remaining ? { left: remaining } : {}
    })
    setInFlight((current) => {
      const remainingSide: EditorSide = side === "left" ? "right" : "left"
      return current[remainingSide] ? { left: current[remainingSide] } : {}
    })
  }, [])

  const updateFileContent = useCallback((side: EditorSide, content: string) => {
    setActiveFileDetails((current) => {
      const file = current[side]
      return file ? { ...current, [side]: { ...file, content } } : current
    })
  }, [])

  const markFileSaved = useCallback((side: EditorSide, hash: string) => {
    setActiveFileDetails((current) => {
      const file = current[side]
      return file ? { ...current, [side]: { ...file, hash } } : current
    })
    void mutateSkillDetail()
  }, [mutateSkillDetail])

  const setFileInFlight = useCallback((side: EditorSide, active: boolean) => {
    setInFlight((current) => ({ ...current, [side]: active }))
  }, [])

  const reloadOpenFile = useCallback(async (side: EditorSide) => {
    const file = activeFileDetails[side]
    if (!file) return
    const detail = await getSkillDetail(file.skillId)
    const content = detail.files?.[file.path]
    if (content === undefined) return
    const hash = await sha256Hex(content)
    setActiveFileDetails((current) => ({
      ...current,
      [side]: { ...file, content, hash, saveEnabled: true, title: undefined },
    }))
    void mutateSkillDetail(detail, { revalidate: false })
  }, [activeFileDetails, mutateSkillDetail])

  const handleUseRemote = useCallback(() => {
    if (!conflict) return
    setActiveFileDetails((current) => {
      const currentFile = current[conflict.side]
      if (!currentFile) return current
      return {
        ...current,
        [conflict.side]: {
          ...currentFile,
          content: conflict.remoteContent,
          hash: conflict.remoteHash,
          saveEnabled: true,
          title: undefined,
        },
      }
    })
    setConflict(null)
  }, [conflict])

  const handleViewDiff = useCallback(() => {
    if (!conflict) return
    setSplitMode(true)
    setActiveFileDetails((current) => ({
      ...current,
      right: {
        path: conflict.path,
        title: `${conflict.path} remote`,
        language: languageForPath(conflict.path),
        content: conflict.remoteContent,
        hash: conflict.remoteHash,
        skillId: conflict.skillId,
        saveEnabled: false,
      },
    }))
    setConflict(null)
  }, [conflict])

  const pushNavSkill = useCallback((nextSkillId: string) => {
    setNavStack((current) => [...current, nextSkillId])
    setActiveFileDetails({})
    setSplitMode(false)
    setSelectedNode(null)
    setSelectedNodeId(null)
  }, [])

  const popNavTo = useCallback((index: number) => {
    setNavStack((current) => current.slice(0, index + 1))
    setActiveFileDetails({})
    setSplitMode(false)
    setSelectedNode(null)
    setSelectedNodeId(null)
  }, [])

  useEffect(() => {
    if (!currentSkillId) return
    const socket = new WebSocket(wsUrl("/ws/events"))
    socket.onmessage = (message) => {
      try {
        const event = JSON.parse(String(message.data)) as { type?: string, skill_id?: string, path?: string }
        if (event.type !== "skill_changed" || event.skill_id !== currentSkillId || !event.path) return
        const entries = (["left", "right"] as const).filter((side) => activeFileDetails[side]?.path === event.path)
        for (const side of entries) {
          const file = activeFileDetails[side]
          if (!file) continue
          void getSkillDetail(currentSkillId).then(async (detail) => {
            const remoteContent = detail.files?.[event.path ?? ""]
            if (remoteContent === undefined) return
            const remoteHash = await sha256Hex(remoteContent)
            if (inFlightRef.current[side]) {
              setConflict({
                skillId: currentSkillId,
                path: event.path ?? file.path,
                side,
                localContent: file.content,
                remoteContent,
                remoteHash,
              })
            } else {
              setActiveFileDetails((current) => ({
                ...current,
                [side]: { ...file, content: remoteContent, hash: remoteHash },
              }))
              void mutateSkillDetail(detail, { revalidate: false })
            }
          })
        }
      } catch {
        toast.error("Could not process file change event")
      }
    }
    return () => socket.close()
  }, [activeFileDetails, currentSkillId, mutateSkillDetail])

  const contextValue = useMemo<WorkspaceContextValue>(() => ({
    currentSkillId,
    navStack,
    activeFiles: {
      left: activeFileDetails.left?.path,
      right: activeFileDetails.right?.path,
    },
    activeFileDetails,
    splitMode,
    onFileOpen: handleFileOpen,
    openSplitEditor: () => setSplitMode(true),
    closeFile,
    updateFileContent,
    markFileSaved,
    setFileInFlight,
    onSaveConflict: setConflict,
    reloadOpenFile,
    pushNavSkill,
    popNavTo,
  }), [
    activeFileDetails,
    closeFile,
    currentSkillId,
    handleFileOpen,
    markFileSaved,
    navStack,
    popNavTo,
    pushNavSkill,
    reloadOpenFile,
    setFileInFlight,
    splitMode,
    updateFileContent,
  ])

  const handleCompile = useCallback(() => {
    if (!currentSkillId) return
    const targetSkillId = currentSkillId
    setCompileStages((current) => ({ ...current, [targetSkillId]: "compiling" }))
    setCompileErrors((current) => ({ ...current, [targetSkillId]: [] }))
    void compileSkill(targetSkillId)
      .then((result) => {
        if ("code" in result) {
          setCompileStages((current) => ({ ...current, [targetSkillId]: "compile-fail" }))
          setCompileErrors((current) => ({ ...current, [targetSkillId]: result.errors }))
          const firstMessage = result.errors[0]?.message ?? result.detail
          toast.error(`${result.errors.length} compile error${result.errors.length === 1 ? "" : "s"}: ${firstMessage}`)
          return
        }
        if (result.status === "ok") {
          setCompileStages((current) => ({ ...current, [targetSkillId]: "compile-pass" }))
          setCompileErrors((current) => ({ ...current, [targetSkillId]: [] }))
          toast.success(`Compiled ${result.manifest_name}`)
          void mutateSkillDetail()
        }
      })
      .catch((error: unknown) => {
        setCompileStages((current) => ({ ...current, [targetSkillId]: "compile-fail" }))
        const message = error instanceof Error ? error.message : "Compile request failed"
        setCompileErrors((current) => ({
          ...current,
          [targetSkillId]: [{ file: null, line: null, field: null, severity: "fatal", message }],
        }))
        toast.error(message)
      })
  }, [currentSkillId, mutateSkillDetail])

  const deriveBuildStage = (id: string): SkillBuildStage => {
    const compileStage = compileStages[id]
    if (compileStage) return compileStage
    const lint = readLintStatus(id)
    if (lint === "checking") return "compiling"
    if (lint === "failed") return "compile-fail"
    if (lint === "passed") return "compile-pass"
    return "idle"
  }

  const hasOpenFile = Boolean(activeFileDetails.left || activeFileDetails.right)
  const currentCompileErrors = currentSkillId ? compileErrors[currentSkillId] ?? [] : []

  return (
    <WorkspaceProvider value={contextValue}>
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground">
      <Header
        skillId={currentSkillId}
        navStack={navStack}
        onBreadcrumbClick={popNavTo}
        copilotOpen={copilotOpen}
        onCopilotToggle={() => setCopilotOpen((open) => !open)}
        onHome={onCloseSkill}
        onSyncSuccess={() => {
          void mutateSkillDetail()
        }}
      />

      <div className="relative flex min-h-0 flex-1">
        <Toolbar
          activePanel={activePanel}
          onPanelChange={setActivePanel}
          onSettingsOpen={() => setSettingsOpen(true)}
        />

        <ResizablePanelGroup
          id="studio-workspace-h"
          orientation="horizontal"
          className="min-w-0 flex-1"
        >
          {activePanel ? (
            <>
              <ResizablePanel
                id="left-panel"
                defaultSize="20%"
                minSize="14%"
                maxSize="35%"
              >
                <Panels
                  activePanel={activePanel}
                  skillId={currentSkillId}
                  skillDetail={skillDetail}
                  selectedNode={selectedNode}
                />
              </ResizablePanel>
              <ResizableHandle />
            </>
          ) : null}

          <ResizablePanel id="canvas" defaultSize={copilotOpen ? "60%" : "80%"} minSize="30%">
            <div className="relative size-full">
              {settingsOpen ? (
                <SettingsPage onClose={() => setSettingsOpen(false)} />
              ) : currentSkillId && hasOpenFile ? (
                <SplitEditor
                  skillId={currentSkillId}
                  skillDetail={skillDetail}
                  isLoading={isLoading}
                  error={skillDetailError}
                  selectedNodeId={selectedNodeId}
                  onNodeSelect={handleNodeSelect}
                  onPanelChange={setActivePanel}
                />
              ) : currentSkillId === null ? (
                <WelcomePage onSelectSkill={onSelectSkill} />
              ) : (
                <GraphCanvas
                  skillId={currentSkillId}
                  skillDetail={skillDetail}
                  isLoading={isLoading}
                  error={skillDetailError}
                  selectedNodeId={selectedNodeId}
                  onNodeSelect={handleNodeSelect}
                  onPanelChange={setActivePanel}
                />
              )}
              {currentSkillId && !settingsOpen ? (
                <>
                  {currentCompileErrors.length > 0 ? (
                    <CompileErrorPanel errors={currentCompileErrors} />
                  ) : null}
                  <CenterActionBar
                    stage={deriveBuildStage(currentSkillId)}
                    onCompile={handleCompile}
                    onPredict={() => console.info("predict clicked")}
                    onRun={() => console.info("run clicked")}
                  />
                </>
              ) : null}
            </div>
          </ResizablePanel>

          {copilotOpen ? (
            <>
              <ResizableHandle />
              <ResizablePanel
                id="copilot"
                defaultSize="20%"
                minSize="18%"
                maxSize="35%"
              >
                <CopilotPanel skillId={skillId} />
              </ResizablePanel>
            </>
          ) : null}
        </ResizablePanelGroup>
      </div>
      <ConflictDialog
        conflict={conflict}
        onKeepLocal={() => setConflict(null)}
        onUseRemote={handleUseRemote}
        onViewDiff={handleViewDiff}
      />
    </div>
    </WorkspaceProvider>
  )
}

function CompileErrorPanel({ errors }: { errors: CompileError[] }) {
  const first = errors[0]
  return (
    <div className="absolute bottom-20 left-1/2 z-30 w-[min(560px,calc(100%-2rem))] -translate-x-1/2 rounded-md border border-destructive/40 bg-background/95 p-3 text-sm shadow-lg backdrop-blur">
      <div className="font-medium text-destructive">
        {errors.length} compile error{errors.length === 1 ? "" : "s"}: {first?.message ?? "Compilation failed"}
      </div>
      <div className="mt-2 max-h-36 space-y-2 overflow-auto">
        {errors.map((error, index) => (
          <div key={`${error.file ?? "compile"}-${error.line ?? "x"}-${index}`} className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">
              {error.file ?? "unknown file"}
              {error.line ? `:${error.line}` : ""}
            </span>
            {error.field ? <span> - {error.field}</span> : null}
            <span> - {error.message}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function languageForPath(path: string): string {
  if (path.endsWith(".json")) return "json"
  if (path.endsWith(".py")) return "python"
  return "markdown"
}
