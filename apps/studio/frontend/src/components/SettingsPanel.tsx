import type { ApiKeyName, ApiKeys } from '../types/studio'

interface SettingsPanelProps {
  apiKeys: ApiKeys
  onApiKeyChange: (key: ApiKeyName, value: string) => void
}

const apiKeyFields = [
  ['openai', 'OpenAI API Key', 'sk-...'],
  ['anthropic', 'Anthropic API Key', 'sk-ant-...'],
  ['gemini', 'Google Gemini API Key', 'AIza...'],
] as const satisfies readonly [ApiKeyName, string, string][]

export function SettingsPanel({ apiKeys, onApiKeyChange }: SettingsPanelProps) {
  return (
    <div className="h-full overflow-y-auto bg-gray-50 dark:bg-slate-950 p-6">
      <h2 className="mb-6 text-xl font-bold text-gray-800 dark:text-gray-100">Settings</h2>
      <div className="rounded-md border border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm">
        <h3 className="mb-4 border-b border-gray-200 dark:border-slate-800 pb-2 text-sm font-bold uppercase text-gray-700 dark:text-gray-300">LLM API Keys</h3>
        <div className="space-y-4">
          {apiKeyFields.map(([key, label, placeholder]) => (
            <label key={key} className="block">
              <span className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">{label}</span>
              <input
                type="password"
                value={apiKeys[key]}
                onChange={(event) => onApiKeyChange(key, event.target.value)}
                className="w-full rounded-md border border-gray-300 dark:border-slate-700 dark:bg-slate-800 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-500"
                placeholder={placeholder}
              />
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}
