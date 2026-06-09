import type { FieldDifference, FieldDiffType, JsonValue } from '../../api/types'
import { isJsonObject } from '../../utils/errors'
import { DiffScore } from './DiffScore'
import { BoolDiffView } from './BoolDiffView'
import { DictDiffView } from './DictDiffView'
import { ListDiffView } from './ListDiffView'
import { NumberDiffView } from './NumberDiffView'
import { TextDiffView } from './TextDiffView'

interface DiffFieldProps {
  field?: FieldDifference
  fieldPath?: string
  currentValue?: JsonValue
  goldenValue?: JsonValue
  depth?: number
}

function inferType(currentValue: JsonValue, goldenValue: JsonValue): FieldDiffType {
  const sample = currentValue ?? goldenValue
  if (typeof sample === 'boolean') {
    return 'bool'
  }
  if (typeof sample === 'number') {
    return 'number'
  }
  if (typeof sample === 'string') {
    return 'text'
  }
  if (Array.isArray(sample)) {
    return 'list'
  }
  if (isJsonObject(sample)) {
    return 'dict'
  }
  return sample === null ? 'null' : 'unknown'
}

function fieldScore(currentValue: JsonValue, goldenValue: JsonValue): number {
  return currentValue === goldenValue ? 1 : 0
}

function valuePreview(value: JsonValue): string {
  if (typeof value === 'string') {
    return value
  }
  return JSON.stringify(value)
}

export function DiffField({
  field,
  fieldPath = 'output',
  currentValue = null,
  goldenValue = null,
  depth = 0,
}: DiffFieldProps) {
  const path = field?.field_path ?? fieldPath
  const current = field?.current_value ?? currentValue
  const golden = field?.golden_value ?? goldenValue
  const type = field?.type ?? inferType(current, golden)
  const changed = field?.changed ?? current !== golden
  const score = field?.score ?? fieldScore(current, golden)

  const renderChild = (
    childPath: string,
    childCurrent: JsonValue,
    childGolden: JsonValue,
    childDepth: number,
  ) => (
    <DiffField
      fieldPath={childPath}
      currentValue={childCurrent}
      goldenValue={childGolden}
      depth={childDepth}
    />
  )

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h4 className="truncate font-mono text-xs font-semibold text-foreground">
            {path}
          </h4>
          <div className="mt-1 flex items-center gap-2">
            <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] font-semibold uppercase text-muted-foreground">
              {type}
            </span>
            <span className={`text-[11px] font-semibold ${changed ? 'text-warning' : 'text-success'}`}>
              {changed ? 'Changed' : 'Unchanged'}
            </span>
          </div>
        </div>
        <DiffScore score={score * 100} compact />
      </div>

      {type === 'text' ? <TextDiffView currentValue={current} goldenValue={golden} /> : null}
      {type === 'number' ? <NumberDiffView currentValue={current} goldenValue={golden} /> : null}
      {type === 'bool' ? <BoolDiffView currentValue={current} goldenValue={golden} /> : null}
      {type === 'list' ? (
        <ListDiffView
          currentValue={current}
          goldenValue={golden}
          fieldPath={path}
          depth={depth}
          renderChild={renderChild}
        />
      ) : null}
      {type === 'dict' ? (
        <DictDiffView
          currentValue={current}
          goldenValue={golden}
          fieldPath={path}
          depth={depth}
          renderChild={renderChild}
        />
      ) : null}
      {type === 'null' || type === 'unknown' || depth >= 5 ? (
        <pre className="max-h-40 overflow-auto rounded-md border border-border bg-muted/50 p-3 text-xs text-foreground">
          {valuePreview(current)}
        </pre>
      ) : null}
    </section>
  )
}
