import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

export interface OfficialVendor {
  code: string
  label: string
  baseUrl: string
}

export const OFFICIAL_VENDORS: OfficialVendor[] = [
  { code: "anthropic", label: "Anthropic", baseUrl: "https://api.anthropic.com" },
  { code: "openai", label: "OpenAI", baseUrl: "https://api.openai.com" },
  { code: "gemini", label: "Gemini", baseUrl: "https://generativelanguage.googleapis.com" },
  { code: "deepseek", label: "DeepSeek", baseUrl: "https://api.deepseek.com" },
  { code: "ark", label: "Ark", baseUrl: "https://ark.cn-beijing.volces.com/api/v3" },
]

interface Props {
  value: string
  onChange: (vendor: OfficialVendor) => void
}

export function OfficialVendorSelect({ value, onChange }: Props) {
  return (
    <Select
      value={value}
      onValueChange={(code) => {
        const vendor = OFFICIAL_VENDORS.find((item) => item.code === code)
        if (vendor) onChange(vendor)
      }}
    >
      <SelectTrigger>
        <SelectValue placeholder="Select official provider..." />
      </SelectTrigger>
      <SelectContent>
        {OFFICIAL_VENDORS.map((vendor) => (
          <SelectItem key={vendor.code} value={vendor.code}>
            {vendor.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
