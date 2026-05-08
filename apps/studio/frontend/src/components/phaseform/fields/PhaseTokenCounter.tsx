interface PhaseTokenCounterProps {
  text: string
}

function estimatedTokens(text: string): number {
  return Math.max(0, Math.ceil(text.length / 4))
}

export function PhaseTokenCounter({ text }: PhaseTokenCounterProps) {
  return (
    <div className="text-xs font-medium text-slate-500 dark:text-slate-400">
      Characters: {text.length.toLocaleString()} / ~{estimatedTokens(text).toLocaleString()} tokens
    </div>
  )
}
