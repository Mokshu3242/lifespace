import { useEffect, useMemo, useRef } from 'react'
import { roomColor } from './mapStyle'

/** A small top-down map in the corner of first person: rooms, walls, their path, and where you are. */
export default function MiniMap({ grid, x, z, yaw, color = '#e4572e', path = [], size = 210 }) {
  const ref = useRef(null)
  // crop to the home itself (skip the outside margin)
  const box = useMemo(() => {
    let r0 = Infinity, r1 = -1, c0 = Infinity, c1 = -1
    grid.forEach((row, r) => row.forEach((v, c) => {
      if (v === -2) return
      r0 = Math.min(r0, r); r1 = Math.max(r1, r); c0 = Math.min(c0, c); c1 = Math.max(c1, c)
    }))
    return r1 < 0 ? { r0: 0, c0: 0, rows: grid.length, cols: grid[0].length } : { r0, c0, rows: r1 - r0 + 1, cols: c1 - c0 + 1 }
  }, [grid])
  const { r0, c0, rows, cols } = box
  const k = size / Math.max(cols, rows)

  // the plan itself, drawn once per map
  const base = useMemo(() => {
    const cv = document.createElement('canvas')
    cv.width = Math.ceil(cols * k)
    cv.height = Math.ceil(rows * k)
    const ctx = cv.getContext('2d')
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const v = grid[r + r0][c + c0]
      if (v === -2) continue
      ctx.fillStyle = v >= 0 ? roomColor(v) : v === -1 ? '#3a3a3a' : '#9a9690'
      ctx.fillRect(c * k, r * k, k + 0.5, k + 0.5)
    }
    return cv
  }, [grid, rows, cols, k, r0, c0])

  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    ctx.clearRect(0, 0, cv.width, cv.height)
    ctx.drawImage(base, 0, 0)
    if (path.length > 1) {
      ctx.strokeStyle = color
      ctx.globalAlpha = 0.45
      ctx.lineWidth = 1.5
      ctx.beginPath()
      path.forEach(([c, r], i) => (i ? ctx.lineTo : ctx.moveTo).call(ctx, (c - c0 + 0.5) * k, (r - r0 + 0.5) * k))
      ctx.stroke()
      ctx.globalAlpha = 1
    }
    if (x == null) return
    const px = (x - c0) * k, pz = (z - r0) * k
    // view cone, then the dot
    ctx.fillStyle = color
    ctx.globalAlpha = 0.25
    ctx.beginPath()
    ctx.moveTo(px, pz)
    ctx.arc(px, pz, 22, yaw - 0.6, yaw + 0.6)
    ctx.closePath()
    ctx.fill()
    ctx.globalAlpha = 1
    ctx.beginPath()
    ctx.arc(px, pz, 4, 0, Math.PI * 2)
    ctx.fill()
    ctx.strokeStyle = '#fff'
    ctx.lineWidth = 1.5
    ctx.stroke()
  }, [base, x, z, yaw, color, path, k, r0, c0])

  return <canvas ref={ref} className="minimap" width={base.width} height={base.height} aria-label="Map of where you are" />
}
