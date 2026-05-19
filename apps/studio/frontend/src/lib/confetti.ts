import confetti from 'canvas-confetti'

export function celebrateSuccess() {
  void confetti({
    particleCount: 80,
    spread: 55,
    origin: { y: 0.7 },
  })
}
