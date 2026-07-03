import { Component, type ErrorInfo, type ReactNode } from "react"
import { TriangleAlert } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"

/**
 * Generic render-error boundary. Any exception thrown while rendering `children`
 * is caught here and shown as an inline destructive card with a Retry — instead of
 * propagating to the React root, which unmounts the ENTIRE app (a black screen).
 *
 * Studio live-parses possibly-mid-edit content during render (the i/o panel, the
 * canvas, and the phase form all read author-written YAML), so one malformed
 * keystroke must never be able to tear down the whole app. The render-path parsers
 * degrade gracefully AND this backstops anything unforeseen. `label` names the
 * region so the message and the console log stay useful.
 */
export class ErrorBoundary extends Component<
  { children: ReactNode; label: string },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error(`${this.props.label} crashed`, error, errorInfo)
  }

  render() {
    if (!this.state.error) return this.props.children

    return (
      <Alert variant="destructive" className="max-w-3xl">
        <TriangleAlert className="size-4" />
        <AlertTitle>{this.props.label} failed to render</AlertTitle>
        <AlertDescription className="space-y-2">
          <p>{this.state.error.message || "Unexpected UI error."}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => this.setState({ error: null })}
          >
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    )
  }
}
