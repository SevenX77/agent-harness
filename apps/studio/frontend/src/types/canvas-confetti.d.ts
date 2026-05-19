declare module 'canvas-confetti' {
  interface ConfettiOptions {
    particleCount?: number
    spread?: number
    origin?: { x?: number, y?: number }
  }

  export default function confetti(options?: ConfettiOptions): Promise<null>
}
