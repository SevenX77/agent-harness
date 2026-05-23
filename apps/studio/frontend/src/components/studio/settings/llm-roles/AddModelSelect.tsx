import { useState } from "react"
import { Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

export function AddModelSelect({
  modelCodes,
  onAppend,
}: {
  modelCodes: string[]
  onAppend: (modelCode: string) => void
}) {
  const [resetKey, setResetKey] = useState(0)

  if (modelCodes.length === 0) {
    return (
      <Button type="button" variant="outline" size="sm" disabled>
        All models added
      </Button>
    )
  }

  return (
    <Select
      key={resetKey}
      onValueChange={(modelCode) => {
        onAppend(modelCode)
        setResetKey((value) => value + 1)
      }}
    >
      <SelectTrigger className="w-full sm:w-56" aria-label="Add model to role">
        <Plus className="size-3" />
        <SelectValue placeholder="Add model" />
      </SelectTrigger>
      <SelectContent>
        {modelCodes.map((modelCode) => (
          <SelectItem key={modelCode} value={modelCode}>
            {modelCode}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
