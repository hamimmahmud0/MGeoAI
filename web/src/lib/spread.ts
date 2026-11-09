export type Disc = { x: number; y: number; r: number }

/** Radius in pixels of an incident circle (same scale as the map style: 0 killed = 6 px, 60+ = 24 px). */
export function discRadius(killed: number): number {
  const stops: [number, number][] = [[0, 6], [5, 9], [20, 15], [60, 24]]
  if (killed >= 60) return 24
  for (let i = 1; i < stops.length; i += 1) {
    if (killed <= stops[i][0]) {
      const [x0, y0] = stops[i - 1]
      const [x1, y1] = stops[i]
      return y0 + ((killed - x0) / (x1 - x0)) * (y1 - y0)
    }
  }
  return 6
}

/**
 * Push overlapping circles apart in screen space until none overlap. Circles that already have room
 * stay where they are; ones sharing a place fan out around it, as little as needed. Deterministic.
 */
export function spreadDiscs(discs: Disc[], gap = 2): { x: number; y: number }[] {
  const origin = discs.map((d) => ({ x: d.x, y: d.y }))
  const pos = discs.map((d) => ({ x: d.x, y: d.y }))
  const golden = 2.399963229728653
  const separate = (): boolean => {
    let moved = false
    for (let i = 0; i < pos.length; i += 1) {
      for (let j = i + 1; j < pos.length; j += 1) {
        let dx = pos[j].x - pos[i].x
        let dy = pos[j].y - pos[i].y
        let dist = Math.hypot(dx, dy)
        const need = discs[i].r + discs[j].r + gap
        if (dist >= need) continue
        if (dist < 0.01) { dx = Math.cos(j * golden); dy = Math.sin(j * golden); dist = 1 }
        const push = (need - dist) / 2
        pos[i].x -= (dx / dist) * push; pos[i].y -= (dy / dist) * push
        pos[j].x += (dx / dist) * push; pos[j].y += (dy / dist) * push
        moved = true
      }
    }
    return moved
  }
  for (let iteration = 0; iteration < 120; iteration += 1) {
    const moved = separate()
    for (let i = 0; i < pos.length; i += 1) { // a light pull back toward the true place keeps the cloud tight
      pos[i].x += (origin[i].x - pos[i].x) * 0.03
      pos[i].y += (origin[i].y - pos[i].y) * 0.03
    }
    if (!moved && iteration > 2) break
  }
  for (let iteration = 0; iteration < 200 && separate(); iteration += 1) { /* final pass without the pull: guarantees no overlap */ }
  return pos
}
