/**
 * Fill empty rooms with the furniture they obviously have (a bed in a bedroom, a sofa in a living room)
 * so the 3D view feels lived in. These pieces are only for the picture: they are never sent to the
 * backend, never counted in scores, and never placed where the measured paths walk.
 * Facing follows facingFor in furniture3d: 0 = back to the north wall, PI = south, PI/2 = west, -PI/2 = east.
 */

const WALL = -1

function plansFor(name, sqft) {
  const n = name.toLowerCase()
  if (/terrace|balcony|patio|deck|porch/.test(n)) return [['outdoor-sofa', 'wall'], ['outdoor-table', 'center']]
  if (/bed|guest|nursery|kid/.test(n)) {
    const bed = sqft >= 150 ? 'bed-queen' : sqft >= 100 ? 'bed-full' : 'bed-twin'
    return [[bed, 'wall'], ['nightstand', 'wall'], ['dresser', 'wall']]
  }
  if (/living|family|lounge|great/.test(n)) {
    return [[sqft >= 180 ? 'sofa-3' : 'sofa-2', 'wall'], ['tv-stand', 'wall'], ['coffee-table', 'center'],
      ['armchair', 'wall'], ['floor-lamp', 'wall'], ['plant', 'wall']]
  }
  if (/dining/.test(n)) return [['dining-4', 'table']]
  if (/office|study|den|work/.test(n)) return [['desk-home', 'wall'], ['bookshelf', 'wall']]
  if (/foyer|entry|hall/.test(n)) return sqft >= 40 ? [['bench-entry', 'wall']] : []
  return []
}

const FAMILY = (id) => id.replace(/-(queen|full|twin|king|2|3|4|6|home|office)$/, '')

export function typicalFurniture(grid, rooms, items, catalog, cellIn, walks = []) {
  const rows = grid.length, cols = grid[0].length
  const cats = Object.fromEntries(catalog.map((c) => [c.id, c]))
  const occ = grid.map((row) => row.map(() => 0))      // 1 = taken by furniture, 2 = someone walks here
  const mark = (r0, c0, h, w, v, ring = 0) => {
    for (let r = r0 - ring; r < r0 + h + ring; r++) for (let c = c0 - ring; c < c0 + w + ring; c++)
      if (r >= 0 && c >= 0 && r < rows && c < cols) occ[r][c] = Math.max(occ[r][c], v)
  }
  const roomOf = {}
  for (const it of items) {
    const r = Math.round(it.y), c = Math.round(it.x)
    const id = grid[r]?.[c]
    if (id >= 0) (roomOf[id] ||= []).push(FAMILY(it.item || ''))
    mark(Math.round(it.y - it.d / 2), Math.round(it.x - it.w / 2), Math.ceil(it.d), Math.ceil(it.w), 1, 1)
  }
  for (const w of walks) for (const [c, r] of w.pts) mark(r - 2, c - 2, 5, 5, 2)

  const out = []
  const size = (id) => {
    const s = cats[id]?.size_in
    return s ? [Math.max(1, Math.round(s.w / cellIn)), Math.max(1, Math.round(s.d / cellIn))] : null
  }
  for (const room of rooms || []) {
    const id = room.id
    const cells = []
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) if (grid[r][c] === id) cells.push([r, c])
    if (cells.length < 20) continue
    const sqft = cells.length * (cellIn / 12) ** 2
    const inRoom = (r, c) => grid[r]?.[c] === id
    const free = (r, c) => inRoom(r, c) && occ[r][c] === 0
    // doorways: room cells touching floor of another room
    const doors = cells.filter(([r, c]) => [[1, 0], [-1, 0], [0, 1], [0, -1]]
      .some(([i, j]) => { const v = grid[r + i]?.[c + j]; return v >= 0 && v !== id }))
    const doorDist = (r, c) => doors.reduce((m, [a, b]) => Math.min(m, Math.abs(a - r) + Math.abs(b - c)), 99)
    const cr = cells.reduce((s, x) => s + x[0], 0) / cells.length
    const cc = cells.reduce((s, x) => s + x[1], 0) / cells.length
    const has = new Set(roomOf[id] || [])

    const rectFree = (r0, c0, h, w, ring = 0) => {
      for (let r = r0 - ring; r < r0 + h + ring; r++) for (let c = c0 - ring; c < c0 + w + ring; c++)
        if (!free(r, c)) return false
      return true
    }
    const put = (item, r0, c0, h, w, facing, ring = 1) => {
      out.push({ item, name: cats[item]?.name, x: c0 + w / 2, y: r0 + h / 2, w, d: h, status: 'assumed', facing })
      mark(r0, c0, h, w, 1, ring)
    }

    function againstWall(item) {
      const sz = size(item)
      if (!sz) return
      const [wc, dc] = sz
      let best = null
      // [facing, footprint h, footprint w, cells behind the back]
      const sides = [
        [0, dc, wc, (r0, c0) => Array.from({ length: wc }, (_, k) => [r0 - 1, c0 + k]), (r0, c0) => [r0 + dc, c0, 4, wc]],
        [Math.PI, dc, wc, (r0, c0) => Array.from({ length: wc }, (_, k) => [r0 + dc, c0 + k]), (r0, c0) => [r0 - 4, c0, 4, wc]],
        [Math.PI / 2, wc, dc, (r0, c0) => Array.from({ length: wc }, (_, k) => [r0 + k, c0 - 1]), (r0, c0) => [r0, c0 + dc, wc, 4]],
        [-Math.PI / 2, wc, dc, (r0, c0) => Array.from({ length: wc }, (_, k) => [r0 + k, c0 + dc]), (r0, c0) => [r0, c0 - 4, wc, 4]],
      ]
      for (const [r, c] of cells) {
        for (const [facing, h, w, back, front] of sides) {
          if (!rectFree(r, c, h, w)) continue
          const b = back(r, c)
          if (b.filter(([a, k]) => grid[a]?.[k] === WALL).length < b.length * 0.8) continue
          const [fr, fc, fh, fw] = front(r, c)
          let ok = 0, all = 0
          for (let a = fr; a < fr + fh; a++) for (let k = fc; k < fc + fw; k++) { all++; if (inRoom(a, k) && occ[a][k] !== 1) ok++ }
          if (ok < all * 0.9) continue
          const score = Math.min(doorDist(r + h / 2, c + w / 2), 12) * 10 - Math.hypot(r + h / 2 - cr, c + w / 2 - cc) * 0.2
          if (!best || score > best.score) best = { score, r, c, h, w, facing }
        }
      }
      if (best) put(item, best.r, best.c, best.h, best.w, best.facing)
    }

    function inMiddle(item, ring, keep = 1) {
      const sz = size(item)
      if (!sz) return null
      const [w, h] = sz
      let best = null
      for (const [r, c] of cells) {
        if (!rectFree(r, c, h, w, ring)) continue
        const score = -Math.hypot(r + h / 2 - cr, c + w / 2 - cc)
        if (!best || score > best.score) best = { score, r, c }
      }
      if (best) put(item, best.r, best.c, h, w, 0, keep)
      return best && { ...best, h, w }
    }

    for (const [item, how] of plansFor(room.name || '', sqft)) {
      if (has.has(FAMILY(item)) || !cats[item]) continue
      if (how === 'wall') againstWall(item)
      else if (how === 'center') inMiddle(item, 2)
      else if (how === 'table') {
        const t = inMiddle(item, 4, 0)
        if (!t) continue
        const [chw, chd] = size('dining-chair') || [3, 4]
        // two chairs on each long side, facing the table
        for (const k of [0.25, 0.75]) {
          const c0 = Math.round(t.c + t.w * k - chw / 2)
          if (rectFree(t.r - chd, c0, chd, chw)) put('dining-chair', t.r - chd, c0, chd, chw, 0)
          if (rectFree(t.r + t.h, c0, chd, chw)) put('dining-chair', t.r + t.h, c0, chd, chw, Math.PI)
        }
      }
    }
  }
  return out
}
