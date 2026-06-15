import { ChevronDown, ChevronUp, ListTree, Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  addAgentStep,
  type AgentStep,
  nextStepId,
  parseAgentSteps,
  removeAgentStep,
  reorderAgentSteps,
  updateAgentStep,
} from "@/lib/agent-steps"

/**
 * Inline L3 step editor for an agent phase (phase-editing F5).
 *
 * Renders the agent body's `<step>` blocks as canvas-inline rows the user can
 * add / remove / reorder / edit. Structural edits go through the pure, tested
 * `agent-steps` transforms (which preserve all non-step body text) and emit the
 * rewritten body via `onSave`; the canvas persists it through the normal phase-
 * file save path. The presentational `AgentStepsInlineView` is side-effect free
 * so it renders synchronously in tests.
 */

interface AgentStepsInlineViewProps {
  steps: AgentStep[]
  readOnly?: boolean
  onMove: (id: string, direction: "up" | "down") => void
  onRemove: (id: string) => void
  onRename: (id: string, name: string) => void
  onEditContent: (id: string, content: string) => void
  onAdd: () => void
}

export function AgentStepsInlineView({
  steps,
  readOnly,
  onMove,
  onRemove,
  onRename,
  onEditContent,
  onAdd,
}: AgentStepsInlineViewProps) {
  return (
    <div className="mt-3 rounded-md border border-primary/25 bg-primary/5 p-2 text-xs">
      <div className="flex items-center justify-between font-medium text-primary">
        <span className="flex items-center gap-2">
          <ListTree className="size-3.5" />
          Steps
        </span>
        {!readOnly ? (
          <Button type="button" size="sm" variant="ghost" className="h-6 px-1.5 text-[11px]" onClick={onAdd}>
            <Plus className="size-3" />
            Add step
          </Button>
        ) : null}
      </div>

      {steps.length === 0 ? (
        <div className="mt-2 rounded border border-border bg-card px-2 py-1 text-muted-foreground">
          No steps yet.
        </div>
      ) : (
        <ol className="mt-2 grid gap-2">
          {steps.map((step, index) => (
            <li key={step.id} className="rounded border border-border bg-card p-2">
              <div className="flex items-center gap-1">
                <span className="font-mono text-[10px] text-muted-foreground">{step.id}</span>
                <Input
                  aria-label={`Step ${step.id} name`}
                  defaultValue={step.name}
                  readOnly={readOnly}
                  className="h-6 flex-1 text-[11px]"
                  onBlur={(event) => onRename(step.id, event.target.value)}
                />
                {!readOnly ? (
                  <>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="size-6"
                      aria-label={`Move step ${step.id} up`}
                      disabled={index === 0}
                      onClick={() => onMove(step.id, "up")}
                    >
                      <ChevronUp className="size-3" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="size-6"
                      aria-label={`Move step ${step.id} down`}
                      disabled={index === steps.length - 1}
                      onClick={() => onMove(step.id, "down")}
                    >
                      <ChevronDown className="size-3" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="size-6 text-destructive"
                      aria-label={`Remove step ${step.id}`}
                      onClick={() => onRemove(step.id)}
                    >
                      <Trash2 className="size-3" />
                    </Button>
                  </>
                ) : null}
              </div>
              <Textarea
                aria-label={`Step ${step.id} content`}
                defaultValue={step.content}
                readOnly={readOnly}
                className="mt-1 min-h-[40px] text-[11px]"
                onBlur={(event) => onEditContent(step.id, event.target.value)}
              />
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

interface AgentStepsInlineProps {
  body: string
  onSave: (nextBody: string) => void
  readOnly?: boolean
}

export function AgentStepsInline({ body, onSave, readOnly }: AgentStepsInlineProps) {
  const steps = parseAgentSteps(body)

  const move = (id: string, direction: "up" | "down") => {
    const ids = steps.map((step) => step.id)
    const index = ids.indexOf(id)
    const target = direction === "up" ? index - 1 : index + 1
    if (index < 0 || target < 0 || target >= ids.length) return
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    onSave(reorderAgentSteps(body, ids))
  }

  return (
    <AgentStepsInlineView
      steps={steps}
      readOnly={readOnly}
      onMove={move}
      onRemove={(id) => onSave(removeAgentStep(body, id))}
      onRename={(id, name) => {
        if (name) onSave(updateAgentStep(body, id, { name }))
      }}
      onEditContent={(id, content) => onSave(updateAgentStep(body, id, { content }))}
      onAdd={() =>
        onSave(
          addAgentStep(body, {
            id: nextStepId(steps.map((step) => step.id)),
            name: "new_step",
            content: "",
          }),
        )
      }
    />
  )
}
