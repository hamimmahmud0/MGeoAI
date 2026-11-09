import { describe, expect, it } from 'vitest'
import { discRadius, spreadDiscs } from './spread'

const overlaps = (a: { x: number; y: number }, b: { x: number; y: number }, ra: number, rb: number) => Math.hypot(a.x - b.x, a.y - b.y) < ra + rb - 0.001

describe('spreadDiscs', () => {
  it('fans out incidents that share exactly the same place so none overlap', () => {
    const discs = [12, 3, 0, 20, 5, 1, 8].map((killed) => ({ x: 400, y: 300, r: discRadius(killed) }))
    const out = spreadDiscs(discs)
    for (let i = 0; i < out.length; i += 1) for (let j = i + 1; j < out.length; j += 1) expect(overlaps(out[i], out[j], discs[i].r, discs[j].r)).toBe(false)
    expect(Math.max(...out.map((p) => Math.hypot(p.x - 400, p.y - 300)))).toBeLessThan(80)  // a tight cloud, not scattered across the map
  })

  it('leaves incidents that already have room exactly where they are, and is deterministic', () => {
    const discs = [{ x: 10, y: 10, r: 8 }, { x: 200, y: 10, r: 8 }, { x: 10, y: 200, r: 12 }]
    expect(spreadDiscs(discs)).toEqual(discs.map(({ x, y }) => ({ x, y })))
    const crowded = Array.from({ length: 25 }, (_, i) => ({ x: 100 + (i % 5) * 3, y: 100 + Math.floor(i / 5) * 3, r: 9 }))
    expect(spreadDiscs(crowded)).toEqual(spreadDiscs(crowded))
    const out = spreadDiscs(crowded)
    for (let i = 0; i < out.length; i += 1) for (let j = i + 1; j < out.length; j += 1) expect(overlaps(out[i], out[j], 9, 9)).toBe(false)
  })

  it('sizes circles by people killed', () => {
    expect(discRadius(0)).toBe(6)
    expect(discRadius(5)).toBe(9)
    expect(discRadius(20)).toBe(15)
    expect(discRadius(200)).toBe(24)
    expect(discRadius(12)).toBeGreaterThan(discRadius(5))
  })
})
