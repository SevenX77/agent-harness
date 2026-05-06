import type { PhaseMode } from '../../../hooks/usePhaseForm'

interface PhaseNameFieldProps {
  name: string
  mode: PhaseMode
  error?: string
  onNameChange: (name: string) => void
  onModeChange: (mode: PhaseMode) => void
}

export function PhaseNameField({
  name,
  mode,
  error,
  onNameChange,
  onModeChange,
}: PhaseNameFieldProps) {
  return (
    <div className="grid grid-cols-[1fr_8rem] gap-3">
      <label className="block">
        <span className="mb-1 block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">
          Phase name
        </span>
        <input
          value={name}
          onChange={(event) => onNameChange(event.target.value)}
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        {error ? <span className="mt-1 block text-xs text-red-600 dark:text-red-400">{error}</span> : null}
      </label>
      <label className="block">
        <span className="mb-1 block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">
          Mode
        </span>
        <select
          value={mode}
          onChange={(event) => onModeChange(event.target.value as PhaseMode)}
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        >
          <option value="llm">llm</option>
          <option value="logic">logic</option>
        </select>
      </label>
    </div>
  )
}
