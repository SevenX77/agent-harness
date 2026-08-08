/**
 * Where a trace list parks when the reader first opens it.
 *
 * `follow-end` — a LIVE run: the newest event is the interesting one, so the
 * list sticks to the bottom and follows (the message-scroller primitive owns
 * the following, including release-on-scroll).
 * `start` — a FINISHED run being replayed: reading begins at the first event.
 * The primitive's own default lands at the bottom, which would hand the reader
 * the end of a run they have not started reading.
 */
export type TraceInitialPosition = 'start' | 'follow-end'

export function initialTracePosition({ followStream }: { followStream: boolean }): TraceInitialPosition {
  return followStream ? 'follow-end' : 'start'
}
