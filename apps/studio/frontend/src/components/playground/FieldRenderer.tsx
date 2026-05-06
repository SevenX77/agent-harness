import { fieldKind } from '../../hooks/useInputPlayground'
import { BoolField } from './fields/BoolField'
import { DictField } from './fields/DictField'
import { EnumField } from './fields/EnumField'
import { ListField } from './fields/ListField'
import { NumberField } from './fields/NumberField'
import { StringField } from './fields/StringField'
import type { FieldProps } from './fields/types'

export function FieldRenderer(props: FieldProps) {
  switch (fieldKind(props.input)) {
    case 'enum':
      return <EnumField {...props} />
    case 'number':
      return <NumberField {...props} />
    case 'bool':
      return <BoolField {...props} />
    case 'list':
      return <ListField {...props} />
    case 'dict':
      return <DictField {...props} />
    case 'string':
    default:
      return <StringField {...props} />
  }
}
