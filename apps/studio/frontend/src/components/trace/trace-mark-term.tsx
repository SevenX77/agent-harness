import { createContext, useContext } from 'react'
import { MarkedText, MarkedValue } from '../ui/marked-text'

const TraceMarkTermContext = createContext<string>('')

/**
 * The term the reader searched for, offered to every text surface in the panel.
 *
 * Ambient rather than a prop because of WHERE the answer has to arrive: the
 * matched text can be the row's headline, its event type, or any of the
 * thirteen wells inside an expanded step — none of the components in between
 * have anything to do with searching, and threading the term through them
 * would put a parameter no one reads into every one of them. This is the same
 * shape `WorkspaceContext` already uses from inside these rows.
 *
 * The default is the empty string, i.e. mark nothing, so a well rendered
 * outside the trace panel (the copilot's, for one) is untouched.
 */
export const TraceMarkTermProvider = TraceMarkTermContext.Provider

export function useTraceMarkTerm(): string {
  return useContext(TraceMarkTermContext)
}

/**
 * One value of an event, with the searched term marked in it.
 *
 * Used wherever a row prints a value VERBATIM — the event type, the headline,
 * the model, a route's reason, a fact. Not used for words this app chose
 * (`{{count}} filters on`, `Answered`, a formatted clock time): the search
 * never matched those, so a mark there would claim a hit that did not happen.
 */
export function TraceMark({ text }: { text: string }) {
  return <MarkedText text={text} term={useTraceMarkTerm()} />
}

/**
 * One value of an event printed inside a sentence this app wrote, with the
 * searched term marked in the value and never in the sentence.
 *
 * Several rows do not print a value on its own — they print `endpoint: {{id}}`,
 * `Loaded — {{path}}`, `HTTP {{status}}`. Those are the two rules above meeting
 * in one string: the interpolated part is quotable, the frame around it is not.
 * Without this, a row that matched on its endpoint id showed no mark at all,
 * which is the case F13 rules out —「一个看不出理由的命中,比没有命中更坏」.
 */
export function TraceMarkValue({ text, value }: { text: string; value: string }) {
  return <MarkedValue text={text} value={value} term={useTraceMarkTerm()} />
}
