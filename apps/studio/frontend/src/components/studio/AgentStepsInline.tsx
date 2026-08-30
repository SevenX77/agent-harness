import { ListTree } from "lucide-react"
import { parseAgentSteps } from "@/lib/agent-steps"

/**
 * Inline L3 step projection for an agent phase (phase-editing F5).
 *
 * READ-ONLY since R3-8 (批示轮三 2026-08-29): the user ruled 「在画布上加step
 * 这个功能去掉吧,很鸡肋,应该让用户在编辑器改」 — canvas-inline step EDITING
 * (add/remove/reorder/rename) is withdrawn; the body is edited in the editor.
 * The projection itself stays because the runtime debug bar's 对话续跑 targets
 * exactly these inline sub-nodes (F5 机制条).
 */
export function AgentStepsInline({ body }: { body: string }) {
  const steps = parseAgentSteps(body)

  return (
    <div className="mt-3 rounded-md border border-primary/25 bg-primary/5 p-2 text-xs">
      <div className="flex items-center gap-2 font-medium text-foreground">
        <ListTree className="size-3.5" />
        Steps
      </div>

      {steps.length === 0 ? (
        <div className="mt-2 rounded border border-border bg-card px-2 py-1 text-muted-foreground">
          No steps yet.
        </div>
      ) : (
        <ol className="mt-2 grid gap-2">
          {steps.map((step) => (
            <li key={step.id} className="rounded border border-border bg-card p-2">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] text-muted-foreground">{step.id}</span>
                <span className="min-w-0 flex-1 truncate text-[11px] font-medium">{step.name}</span>
              </div>
              {step.content ? (
                <p className="mt-1 whitespace-pre-wrap break-words text-[11px] text-muted-foreground">
                  {step.content}
                </p>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
