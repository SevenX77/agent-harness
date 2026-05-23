import { Component, type ErrorInfo, type ReactNode } from "react"
import { TriangleAlert } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"

export class SettingsErrorBoundary extends Component<
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
