const LLM_ROLES = [
  'analyst',
  'planner',
  'critic',
  'writer',
  'reviewer',
  'researcher',
  'coder',
]

interface LlmRoleFieldProps {
  value: string
  onChange: (value: string) => void
}

export function LlmRoleField({ value, onChange }: LlmRoleFieldProps) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">
        LLM role
      </span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      >
        <option value="">Default</option>
        {LLM_ROLES.map((role) => (
          <option key={role} value={role}>{role}</option>
        ))}
        {value && !LLM_ROLES.includes(value) ? <option value={value}>{value}</option> : null}
      </select>
    </label>
  )
}
