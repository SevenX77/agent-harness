import { Input } from '../../ui/input'
import { Label } from '../../ui/label'

interface ConditionalFieldProps {
  when: string
  skipIf: string
  validator: string
  onWhenChange: (value: string) => void
  onSkipIfChange: (value: string) => void
  onValidatorChange: (value: string) => void
}

export function ConditionalField({
  when,
  skipIf,
  validator,
  onWhenChange,
  onSkipIfChange,
  onValidatorChange,
}: ConditionalFieldProps) {
  return (
    <section className="space-y-3">
      <div className="text-xs font-semibold uppercase text-muted-foreground">
        Conditions and validation
      </div>
      <Label className="block space-y-1">
        <span className="block text-xs font-medium text-muted-foreground">when</span>
        <Input
          value={when}
          onChange={(event) => onWhenChange(event.target.value)}
          placeholder="context.ready == true"
          spellCheck={false}
          autoCorrect="off"
          autoCapitalize="none"
          className="font-mono"
        />
      </Label>
      <Label className="block space-y-1">
        <span className="block text-xs font-medium text-muted-foreground">skip_if</span>
        <Input
          value={skipIf}
          onChange={(event) => onSkipIfChange(event.target.value)}
          placeholder="context.skip_review"
          spellCheck={false}
          autoCorrect="off"
          autoCapitalize="none"
          className="font-mono"
        />
      </Label>
      <Label className="block space-y-1">
        <span className="block text-xs font-medium text-muted-foreground">validator</span>
        <Input
          value={validator}
          onChange={(event) => onValidatorChange(event.target.value)}
          placeholder="script.validators.validate_output"
          spellCheck={false}
          autoCorrect="off"
          autoCapitalize="none"
          className="font-mono"
        />
      </Label>
    </section>
  )
}
