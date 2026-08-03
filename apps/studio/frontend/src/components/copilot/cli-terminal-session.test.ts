// Design: docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md §10.
import { describe, expect, it } from 'vitest'
import { cliTerminalOutputBytes, createCliOutputPump } from './cli-terminal-session'

describe('cliTerminalOutputBytes', () => {
  it('decodes base64 into the exact bytes the PTY produced', () => {
    // A chunk boundary can fall inside a multi-byte character, so the bridge
    // must carry bytes rather than decoded text.
    expect(Array.from(cliTerminalOutputBytes('zpHl'))).toEqual([0xce, 0x91, 0xe5])
  })

  it('yields an empty buffer for an empty chunk', () => {
    expect(cliTerminalOutputBytes('').length).toBe(0)
  })
})

describe('createCliOutputPump', () => {
  it('replays output produced before a renderer attached', () => {
    // A session starts talking immediately; on Windows its opening bytes are a
    // cursor-position query ConPTY blocks on until answered. Losing them stalls
    // the whole session, so the pump holds them for the renderer.
    const pump = createCliOutputPump()
    pump.push('YQ==')
    pump.push('Yg==')

    const seen: number[] = []
    pump.attach((bytes) => seen.push(...bytes))

    expect(seen).toEqual([0x61, 0x62])
  })

  it('streams live once attached, and stops after detaching', () => {
    const pump = createCliOutputPump()
    const seen: number[] = []
    const detach = pump.attach((bytes) => seen.push(...bytes))

    pump.push('YQ==')
    detach()
    pump.push('Yg==')

    expect(seen).toEqual([0x61])
  })

  it('replays the whole history to a second renderer', () => {
    // React mounts effects twice in development and throws the first terminal
    // away. If attaching CONSUMED the backlog, the surviving terminal would
    // never see the session's opening bytes — including the cursor-position
    // query ConPTY waits on — and the session would hang, silently.
    const pump = createCliOutputPump()
    pump.push('YQ==')

    const first: number[] = []
    const detachFirst = pump.attach((bytes) => first.push(...bytes))
    detachFirst()
    pump.push('Yg==')

    const second: number[] = []
    pump.attach((bytes) => second.push(...bytes))

    expect(first).toEqual([0x61])
    expect(second).toEqual([0x61, 0x62])
  })
})
