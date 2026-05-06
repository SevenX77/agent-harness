import { Search, X } from 'lucide-react'

interface TraceSearchBarProps {
  value: string
  onChange: (value: string) => void
}

export function TraceSearchBar({ value, onChange }: TraceSearchBarProps) {
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-md border border-gray-300 bg-white py-2 pl-9 pr-9 text-sm text-gray-800 outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100 dark:border-slate-700 dark:bg-slate-900 dark:text-gray-200 dark:focus:border-sky-500 dark:focus:ring-sky-900/40"
        placeholder="Search trace events"
      />
      {value ? (
        <button
          type="button"
          onClick={() => onChange('')}
          className="absolute right-2 top-2 rounded p-0.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-slate-800 dark:hover:text-gray-200"
          title="Clear search"
        >
          <X className="h-4 w-4" />
        </button>
      ) : null}
    </div>
  )
}
