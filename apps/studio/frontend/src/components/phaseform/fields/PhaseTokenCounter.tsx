interface PhaseTokenCounterProps {
  text: string
}

export function estimatedTokens(text: string): number {
  return Math.max(0, Math.ceil(text.length / 4))
}

export function PhaseTokenCounter({ text }: PhaseTokenCounterProps) {
  return (
    <div className="text-xs font-medium text-muted-foreground">
      Characters: {text.length.toLocaleString()} / ~{estimatedTokens(text).toLocaleString()} tokens
    </div>
  )
}
