import { useEffect, useRef } from 'react'
import { CODES, roomColor } from './mapStyle'

/**
 * Draws the grid map on a canvas, with the original plan optionally underneath.
 * Reports cell clicks/drags through onPaint(row, col, isFirst).
 */
export default function PlanCanvas({ space, grid, rooms, entrance, selectedId, showPlan,
  planImage, onPaint, items = [], selectedItem = null, people = [] }) {
  const ref = useRef(null)
  const dragging = useRef(false)
  const last = useRef(null)
  const { cols, rows } = space
  const S = Math.max(4, Math.floor(900 / cols)) // screen px per cell

  useEffect(() => {
    const cv = ref.current
    const ctx = cv.getContext('2d')
    cv.width = cols * S
    cv.height = rows * S
    ctx.clearRect(0, 0, cv.width, cv.height)

    if (showPlan && planImage) {
      // grid cell = cellPx pixels of the working image; the stored image may be bigger
      const cellPx = space.px_per_ft * space.cell_in / 12
      const k = space.image_size[0] / planImage.naturalWidth
      const scale = (S / cellPx) * k
      ctx.globalAlpha = 0.9
      ctx.drawImage(planImage, 0, 0, planImage.naturalWidth * scale, planImage.naturalHeight * scale)
      ctx.globalAlpha = 1
    }

    const fillAlpha = showPlan ? 0.45 : 1
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const v = grid[r][c]
        if (v === CODES.OUTSIDE) continue
        if (v === CODES.WALL) {
          ctx.globalAlpha = showPlan ? 0.6 : 1
          ctx.fillStyle = '#2b2f2d'
        } else if (v === CODES.FIXTURE) {
          ctx.globalAlpha = fillAlpha
          ctx.fillStyle = '#b9b6ad'
        } else {
          ctx.globalAlpha = v === selectedId ? Math.min(1, fillAlpha + 0.35) : fillAlpha
          ctx.fillStyle = roomColor(v)
        }
        ctx.fillRect(c * S, r * S, S, S)
      }
    }
    ctx.globalAlpha = 1

    // outline the selected room
    if (selectedId != null) {
      ctx.strokeStyle = '#1d2320'
      ctx.lineWidth = 2
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          if (grid[r][c] !== selectedId) continue
          if (r === 0 || grid[r - 1][c] !== selectedId) line(ctx, c * S, r * S, (c + 1) * S, r * S)
          if (r === rows - 1 || grid[r + 1][c] !== selectedId) line(ctx, c * S, (r + 1) * S, (c + 1) * S, (r + 1) * S)
          if (c === 0 || grid[r][c - 1] !== selectedId) line(ctx, c * S, r * S, c * S, (r + 1) * S)
          if (c === cols - 1 || grid[r][c + 1] !== selectedId) line(ctx, (c + 1) * S, r * S, (c + 1) * S, (r + 1) * S)
        }
      }
    }

    // furniture already on the plan: dashed boxes with short names
    ctx.font = `600 ${Math.min(12, Math.max(9, S * 1.2))}px system-ui, sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    for (const it of items) {
      const x = (it.x - it.w / 2) * S, y = (it.y - it.d / 2) * S
      const on = it.id === selectedItem
      const isNew = it.status === 'new'
      if (isNew) {
        ctx.globalAlpha = 0.35
        ctx.fillStyle = '#2f9e6b'
        ctx.fillRect(x, y, it.w * S, it.d * S)
        ctx.globalAlpha = 1
      }
      ctx.setLineDash(on || isNew ? [] : [4, 3])
      ctx.lineWidth = on ? 3 : isNew ? 2.5 : 1.5
      ctx.strokeStyle = on ? '#1f7a5a' : isNew ? '#1f7a4d' : it.unsure ? '#b7791f' : '#2f5d8a'
      ctx.strokeRect(x, y, it.w * S, it.d * S)
      ctx.setLineDash([])
      if (isNew && it.w * S < 14) {
        ctx.fillStyle = '#1f7a4d'
        ctx.beginPath()
        ctx.arc(it.x * S, it.y * S, Math.max(4, S * 0.6), 0, Math.PI * 2)
        ctx.fill()
      }
      const label = shortName(it.name)
      if (on || ctx.measureText(label).width + 4 <= it.w * S) {
        if (on) pill(ctx, label, it.x * S, (it.y - it.d / 2) * S - 10, '#1f7a5a', '#fff')
        else {
          ctx.lineWidth = 3
          ctx.strokeStyle = 'rgba(255,255,255,0.9)'
          ctx.strokeText(label, it.x * S, it.y * S)
          ctx.fillStyle = '#1d3b5a'
          ctx.fillText(label, it.x * S, it.y * S)
        }
      }
    }

    if (entrance) {
      const [ec, er] = entrance
      ctx.fillStyle = '#d64545'
      ctx.beginPath()
      ctx.arc((ec + 0.5) * S, (er + 0.5) * S, Math.max(5, S), 0, Math.PI * 2)
      ctx.fill()
    }
    // people: a fading trail and a dot where they are now
    for (const p of people) {
      ctx.strokeStyle = p.color
      ctx.lineWidth = Math.max(2, S * 0.5)
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'
      ctx.globalAlpha = 0.55
      ctx.beginPath()
      p.trail.forEach(([c, r], i) => {
        const x = (c + 0.5) * S, y = (r + 0.5) * S
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      })
      ctx.stroke()
      ctx.globalAlpha = 1
      const [c, r] = p.at
      ctx.fillStyle = p.color
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.arc((c + 0.5) * S, (r + 0.5) * S, Math.max(6, S * 1.2), 0, Math.PI * 2)
      ctx.fill()
      ctx.stroke()
    }

    // room names last, on a light pill, so furniture never covers them.
    // A name that doesn't fit its room is shortened to its last word, or left out.
    ctx.font = `600 ${Math.min(14, Math.max(10, S * 1.5))}px system-ui, sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    for (const room of rooms) {
      const pos = centerOf(grid, room.id)
      if (!pos) continue
      const [cx, cy] = pos
      const span = rowSpan(grid, room.id, cx, cy) * S
      let label = room.name
      if (ctx.measureText(label).width + 10 > span) label = label.split(' ').slice(-1)[0]
      if (ctx.measureText(label).width + 10 > span && room.id !== selectedId) continue
      pill(ctx, label, (cx + 0.5) * S, (cy + 0.5) * S, 'rgba(255,255,255,0.88)', '#1d2320')
    }
  }, [space, grid, rooms, entrance, selectedId, showPlan, planImage, cols, rows, S, items, selectedItem, people])

  function cellAt(e) {
    const rect = ref.current.getBoundingClientRect()
    const c = Math.floor(((e.clientX - rect.left) / rect.width) * cols)
    const r = Math.floor(((e.clientY - rect.top) / rect.height) * rows)
    return r >= 0 && r < rows && c >= 0 && c < cols ? [r, c] : null
  }

  return (
    <canvas
      ref={ref}
      className="plan-canvas"
      onPointerDown={(e) => {
        const cell = cellAt(e)
        if (!cell) return
        dragging.current = true
        last.current = cell
        e.currentTarget.setPointerCapture(e.pointerId)
        onPaint(cell[0], cell[1], true)
      }}
      onPointerMove={(e) => {
        if (!dragging.current) return
        const cell = cellAt(e)
        if (!cell) return
        // fast drags skip cells between events; fill the line so walls come out solid
        for (const [r, c] of cellsBetween(last.current || cell, cell)) onPaint(r, c, false)
        last.current = cell
      }}
      onPointerUp={() => { dragging.current = false }}
      onPointerCancel={() => { dragging.current = false }}
    />
  )
}

function pill(ctx, text, x, y, bg, fg) {
  const w = ctx.measureText(text).width + 12
  const h = 18
  ctx.fillStyle = bg
  ctx.beginPath()
  if (ctx.roundRect) ctx.roundRect(x - w / 2, y - h / 2, w, h, 9)
  else ctx.rect(x - w / 2, y - h / 2, w, h)
  ctx.fill()
  ctx.fillStyle = fg
  ctx.fillText(text, x, y + 0.5)
}

// how many cells wide a room is along the row through (c, r)
function rowSpan(grid, id, c, r) {
  const row = grid[r]
  let a = c, b = c
  while (a > 0 && row[a - 1] === id) a--
  while (b < row.length - 1 && row[b + 1] === id) b++
  return b - a + 1
}

function shortName(name) {
  return name.replace(/ with (\d+) chairs/, ' +$1').replace(/ \(LED\)/, '')
}

function cellsBetween([r0, c0], [r1, c1]) {
  const out = []
  const n = Math.max(Math.abs(r1 - r0), Math.abs(c1 - c0), 1)
  for (let i = 1; i <= n; i++) {
    out.push([Math.round(r0 + ((r1 - r0) * i) / n), Math.round(c0 + ((c1 - c0) * i) / n)])
  }
  return out
}

function line(ctx, x0, y0, x1, y1) {
  ctx.beginPath()
  ctx.moveTo(x0, y0)
  ctx.lineTo(x1, y1)
  ctx.stroke()
}

// The cell of the room closest to its average position (so L-shaped rooms get a label inside them)
function centerOf(grid, id) {
  let sr = 0, sc = 0, n = 0
  const cells = []
  for (let r = 0; r < grid.length; r++) {
    for (let c = 0; c < grid[r].length; c++) {
      if (grid[r][c] === id) { sr += r; sc += c; n++; cells.push([r, c]) }
    }
  }
  if (!n) return null
  const mr = sr / n, mc = sc / n
  let best = cells[0], bd = Infinity
  for (const [r, c] of cells) {
    const d = (r - mr) ** 2 + (c - mc) ** 2
    if (d < bd) { bd = d; best = [r, c] }
  }
  return [best[1], best[0]]
}
