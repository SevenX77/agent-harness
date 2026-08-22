import { createContext, useContext } from 'react'
import { MarkedText } from '../ui/marked-text'

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
