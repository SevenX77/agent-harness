// @vitest-environment jsdom
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { configureApiBaseURL } from "../api/client"
import { useRunStream } from "./useRunStream"

/**
 * A run stream is about ONE run.
 *
 * Real React here, not the hand-rolled mock the sibling test file uses: that
 * mock re-seeds state from the initial value on every call, so a re-render with
 * a different run cannot be expressed in it at all — and a test written there
 * would pass no matter what the hook does.
 *
 * Observed 2026-08-09 on the real app: a Predict trace of 17 rows followed by a
 * Run left the panel at 70 rows — 17 + the run's own 53 — because the previous
 * subject's events were still in the list the new subject appended to.
 */

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

class FakeWebSocket {
  static instances: FakeWebSocket[] = []

  readonly url: string
  onopen: (() => void) | null = null
  onmessage: ((message: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  emit(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) })
  }

  close(): void {
    this.onclose?.()
  }
}

function envelope(runId: string, seq: number, eventType = "phase_start") {
  return {
    schema_version: "studio.event.v1",
    stream_id: `run:${runId}`,
    seq,
    cursor: `run:${runId}:${seq}`,
    run_id: runId,
    event_type: eventType,
    timestamp: "2026-08-09T00:00:00Z",
    payload: { event_type: eventType, phase_name: "draft" },
  }
}

type Stream = ReturnType<typeof useRunStream>

function mountStream(skillId: string | null, runId: string | null) {
  const container = document.createElement("div")
  document.body.appendChild(container)
  const root: Root = createRoot(container)
  let latest: Stream | null = null

  function Harness({ skill, run }: { skill: string | null, run: string | null }) {
    latest = useRunStream(skill, run)
    return null
  }

  const show = (skill: string | null, run: string | null) => {
    act(() => {
      root.render(<Harness skill={skill} run={run} />)
    })
  }

  show(skillId, runId)
  return {
    show,
    root,
    state: () => {
      if (!latest) throw new Error("hook did not run")
      return latest
    },
  }
}

function socketFor(index: number): FakeWebSocket {
  const socket = FakeWebSocket.instances[index]
  if (!socket) throw new Error(`no socket #${index}; got ${FakeWebSocket.instances.length}`)
  return socket
}

function deliver(socket: FakeWebSocket, payloads: object[]) {
  act(() => {
    socket.onopen?.()
    for (const payload of payloads) socket.emit(payload)
    vi.advanceTimersByTime(100)
  })
}

describe("a run stream is about one run", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    FakeWebSocket.instances = []
    configureApiBaseURL("http://localhost:8787/api")
    vi.stubGlobal("WebSocket", FakeWebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
    document.body.innerHTML = ""
  })

  it("drops the previous run's events when the run changes", () => {
    const stream = mountStream("skill-1", "predict-1")
    deliver(socketFor(0), [envelope("predict-1", 1), envelope("predict-1", 2)])
    expect(stream.state().events).toHaveLength(2)

    stream.show("skill-1", "run-1")
    deliver(socketFor(1), [envelope("run-1", 1)])

    expect(stream.state().events.map((event) => event.run_id)).toEqual(["run-1"])
  })

  it("does not carry the previous run's cursor into the new subscription", () => {
    const stream = mountStream("skill-1", "predict-1")
    deliver(socketFor(0), [envelope("predict-1", 7)])
    expect(stream.state().cursor).toBe("run:predict-1:7")

    stream.show("skill-1", "run-1")

    expect(socketFor(1).url).not.toContain("cursor")
    expect(stream.state().cursor).toBeNull()
  })

  it("drops the previous run's error when the run changes", () => {
    const stream = mountStream("skill-1", "predict-1")
    act(() => {
      socketFor(0).onerror?.()
    })
    expect(stream.state().error).not.toBeNull()

    stream.show("skill-1", "run-1")

    expect(stream.state().error).toBeNull()
  })

  it("empties the list when there is no run to watch", () => {
    const stream = mountStream("skill-1", "run-1")
    deliver(socketFor(0), [envelope("run-1", 1)])
    expect(stream.state().events).toHaveLength(1)

    stream.show("skill-1", null)

    expect(stream.state().events).toEqual([])
    expect(stream.state().status).toBe("idle")
  })

  it("keeps the events it has while the same run keeps rendering", () => {
    const stream = mountStream("skill-1", "run-1")
    deliver(socketFor(0), [envelope("run-1", 1)])

    stream.show("skill-1", "run-1")

    expect(stream.state().events).toHaveLength(1)
    expect(FakeWebSocket.instances).toHaveLength(1)
  })
})
