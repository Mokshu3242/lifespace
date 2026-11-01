import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { GTAOPass } from 'three/examples/jsm/postprocessing/GTAOPass.js'
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js'
import { CODES, roomColor } from './mapStyle'
import { buildItem, facingFor, actionFor, kindOf, loadModels } from './furniture3d'
import { typicalFurniture } from './typicalFurniture'
import MiniMap from './MiniMap'

// 1 grid cell = 6 in = 1 unit, so heights in inches divide by the cell size
const WALL_IN = 96          // 8 ft walls
const CUTAWAY_IN = 40       // walls cut at about 3 ft, the way architects show a model
const FIXTURE_IN = 36       // counters, tubs and other built-ins
const PERSON_IN = 66
const SPEEDS = { Slow: 24, Normal: 45, Fast: 100 }   // inches per second; real walking is about 50
const SQUEEZE_IN = 4         // same as the simulation: a body may brush past by this much
const PAUSE_S = 2.5          // stop at each place in the day, so you can read what they are doing
const STATUS_COLOR = { new: 0x2f9e6b, removed: 0xc0392b, replaced: 0xc0392b, kept: 0xd8cbb3 }

const TILE = /bath|wc|toilet|powder|kitchen|laundry|utility|pantry|shower/i
const DECK = /balcony|patio|deck|terrace|porch|yard|garden|outdoor/i

function eyeIn(w) {
  if (/wheel/i.test(w.mobility || '')) return 48
  if (w.age && w.age < 13) return 44
  return 62
}

/**
 * The same map in 3D. Lived-in mode builds real furniture at catalog size; first person rides
 * along a person's measured path at their eye height. Nothing is invented: walls come from the
 * grid, items from the catalog, paths from the simulation.
 */
export default function View3D({ space, grid, rooms, items = [], people = [], ghost = null, catalog = [],
  planImage, showPlan, walks = [] }) {
  const mount = useRef(null)
  const three = useRef(null)
  const ride = useRef(null)
  const gridRef = useRef(grid)
  const [speed, setSpeed] = useState('Slow')
  const speedRef = useRef(SPEEDS.Slow)
  speedRef.current = SPEEDS[speed]
  gridRef.current = grid
  const roomsRef = useRef(rooms || [])
  roomsRef.current = rooms || []
  const keys = useRef({})
  const solidRef = useRef(null)      // furniture footprints people cannot walk through
  const usable = useRef([])          // things people sit on, lie on or use: { x, z, act, kind, name }
  const [orbit, setOrbit] = useState(false)
  const [fullWalls, setFullWalls] = useState(false)
  const [lived, setLived] = useState(true)
  const [night, setNight] = useState(false)
  const [models, setModels] = useState(0)      // real furniture models loaded (redraw when they arrive)
  useEffect(() => { loadModels().then(setModels) }, [])
  const [ao, setAo] = useState(true)          // soft corner shadows (turn off on slow computers)
  const aoOn = useRef(true)
  aoOn.current = ao     // 2 AM: lights off, only night lights glow
  const [typical, setTypical] = useState(true)   // fill empty rooms with obvious furniture (picture only)
  const [rider, setRider] = useState(null)        // walk id being ridden
  const [hud, setHud] = useState(null)
  const [recording, setRecording] = useState(false)
  const [driving, setDriving] = useState(false)
  const cell = space.cell_in
  const tall = fullWalls || !!rider

  // ---- the scene: built once per map
  useEffect(() => {
    const el = mount.current
    const rows = grid.length, cols = grid[0].length
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true })
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio))
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    el.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(getComputedStyle(document.documentElement).getPropertyValue('--card').trim() || '#ffffff')
    const camera = new THREE.PerspectiveCamera(40, 1, 0.2, 5000)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.target.set(cols / 2, 0, rows / 2)
    controls.maxPolarAngle = Math.PI / 2.1
    controls.enableDamping = true

    // soft, even light from a studio "room" picture (no file to load), so walls don't go brown or glare
    const pmrem = new THREE.PMREMGenerator(renderer)
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
    scene.environmentIntensity = 0.55
    const hemi = new THREE.HemisphereLight(0xfff6e8, 0x8a8577, 1.0)
    scene.add(hemi)
    const sun = new THREE.DirectionalLight(0xfff2dd, 1.6)
    sun.position.set(cols * 0.3, Math.max(cols, rows) * 1.2, rows * 0.1)
    sun.castShadow = true
    sun.shadow.mapSize.set(2048, 2048)
    sun.shadow.bias = -0.0005
    Object.assign(sun.shadow.camera, { left: -cols, right: cols, top: rows, bottom: -rows, far: 4000 })
    sun.target.position.set(cols / 2, 0, rows / 2)
    scene.add(sun, sun.target)

    const groups = { floor: new THREE.Group(), walls: new THREE.Group(), items: new THREE.Group(),
      people: new THREE.Group(), ghost: new THREE.Group() }
    Object.values(groups).forEach((g) => scene.add(g))

    // soft shadows where walls meet floors and around furniture (ambient occlusion)
    const composer = new EffectComposer(renderer)
    composer.addPass(new RenderPass(scene, camera))
    const gtao = new GTAOPass(scene, camera, el.clientWidth || 800, 500)
    gtao.updateGtaoMaterial({ radius: 2.5, distanceExponent: 1.5, thickness: 2, scale: 1.2, samples: 12 })
    gtao.blendIntensity = 0.85
    composer.addPass(gtao)
    composer.addPass(new OutputPass())

    function resize() {
      const w = el.clientWidth, h = Math.max(360, Math.round(w * 0.62))
      renderer.setSize(w, h)
      composer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(el)

    // free look: drag on the view to turn your head (yaw and pitch) while walking or riding along
    const drag = { on: false, x: 0, y: 0 }
    const cv = renderer.domElement
    cv.addEventListener('pointerdown', (e) => {
      if (!ride.current) return
      drag.on = true; drag.x = e.clientX; drag.y = e.clientY
      cv.setPointerCapture(e.pointerId)
    })
    cv.addEventListener('pointermove', (e) => {
      const r = ride.current
      if (!drag.on || !r) return
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y
      drag.x = e.clientX; drag.y = e.clientY
      if (r.drive) r.yaw += dx * 0.005
      else r.lookYaw = (r.lookYaw || 0) + dx * 0.005
      r.pitch = Math.max(-0.7, Math.min(0.6, (r.pitch || 0) - dy * 0.004))
    })
    const release = () => { drag.on = false }
    cv.addEventListener('pointerup', release)
    cv.addEventListener('pointercancel', release)
    const fitsAt = (x, z, half) => fitsAtGrid(gridRef.current, solidRef.current, x, z, half)
    // what someone does at a stop, from the words of that part of their day
    const WANTS = [[/sleep|bed|nap|lie|rest/i, ['lie']], [/tv|watch|read|relax|chat|sofa|sit|game|play/i, ['sit', 'watch']],
      [/eat|lunch|dinner|breakfast|meal|snack|family/i, ['sit', 'use']], [/cook|tea|coffee|kitchen|dishes|fridge/i, ['use']],
      [/bath|toilet|wash|shower|brush/i, ['sit', 'use']], [/work|study|homework|desk|email|code|focus/i, ['sit', 'use']], [/meet|standup|review|call|sync/i, ['sit']]]
    const pickUse = (x, z, note, radius) => {
      const want = WANTS.find(([re]) => re.test(note || ''))?.[1] || []
      let best = null
      for (const u of usable.current) {
        // distance to the edge of the piece, not its middle (a bed is 7 ft long)
        const d = Math.hypot(Math.max(0, Math.abs(u.x - x) - (u.w || 1) / 2), Math.max(0, Math.abs(u.z - z) - (u.d || 1) / 2))
        if (d > radius) continue
        const score = d - (want.includes(u.act) ? 100 - want.indexOf(u.act) * 10 : 0)
        if (!best || score < best.score) best = { ...u, score, d }
      }
      return best
    }
    const poseEye = (r, pose) => {
      const wheel = /wheel/i.test(r.walk.mobility || '')
      const child = r.walk.age && r.walk.age < 13
      if (pose === 'lie') return 36 / cell     // head on the pillow, just above the mattress
      if (pose === 'sit') return wheel ? r.eye : (child ? 32 : 44) / cell
      return r.eye
    }
    const turnTo = (r, x, z, from, dt, rate = 3) => {
      let d = Math.atan2(z - from[1], x - from[0]) - r.yaw
      d = Math.atan2(Math.sin(d), Math.cos(d))
      r.yaw += d * Math.min(1, dt * rate)
    }
    let raf, last = performance.now(), hudAt = 0
    const look = new THREE.Vector3()
    const loop = (now) => {
      const dt = Math.min(0.1, (now - last) / 1000)
      last = now
      const r = ride.current
      if (r && r.drive) {
        // walking as this person: arrows or WASD; a step is allowed only where their body width fits
        const k = keys.current
        const turn = (k.ArrowLeft || k.a ? -1 : 0) + (k.ArrowRight || k.d ? 1 : 0)
        const go = (k.ArrowUp || k.w ? 1 : 0) - (k.ArrowDown || k.s ? 1 : 0)
        r.yaw += turn * dt * 1.8
        if (go && r.pose) { r.pose = null; r.x = r.standX; r.z = r.standZ }   // walking again: stand up first
        if (go && !r.pose) {
          r.tight = !fitsAt(r.x, r.z, r.comfy)
          const step = go * dt * (SPEEDS.Normal / cell) * (r.tight ? 0.45 : 1)   // slow down in a squeeze
          const fx = Math.cos(r.yaw) * step, fz = Math.sin(r.yaw) * step
          const sx = -Math.sin(r.yaw), sz = Math.cos(r.yaw)
          let moved = false
          // straight on; else drift sideways a little to line up with a doorway; else slide along the wall
          for (const side of [0, 0.15, -0.15, 0.3, -0.3, 0.5, -0.5]) {
            const nx = r.x + fx + sx * side * Math.abs(step) * 4, nz = r.z + fz + sz * side * Math.abs(step) * 4
            if (fitsAt(nx, nz, r.half)) { r.x = nx; r.z = nz; moved = true; break }
          }
          if (!moved && fitsAt(r.x + fx, r.z, r.half)) { r.x += fx; moved = true }
          else if (!moved && fitsAt(r.x, r.z + fz, r.half)) { r.z += fz; moved = true }
          r.stuck = moved ? 0 : (r.stuck || 0) + dt
        }
        r.eyeNow = (r.eyeNow ?? r.eye) + (poseEye(r, r.pose) - (r.eyeNow ?? r.eye)) * Math.min(1, dt * 3)
        camera.position.set(r.x, r.eyeNow, r.z)
        look.set(r.x + Math.cos(r.yaw) * 10, r.eyeNow * 0.97 + Math.tan(r.pitch || 0) * 10, r.z + Math.sin(r.yaw) * 10)
        camera.lookAt(look)
        if (now - hudAt > 110) {
          hudAt = now
          r.near = r.pose ? null : pickUse(r.x, r.z, '', 3)
          const id = gridRef.current[Math.floor(r.z)]?.[Math.floor(r.x)]
          const room = roomsRef.current.find((q) => q.id === id)?.name || ''
          setHud({ name: r.walk.name, pct: 0, drive: true,
            x: r.x, z: r.z, yaw: r.yaw,
            near: r.pose ? `E or ▲ to stand up` : r.near ? `E: ${{ lie: 'lie on', sit: 'sit on', watch: 'watch', use: 'use' }[r.near.act]} the ${r.near.name}` : '',
            note: r.pose ? `${r.pose === 'lie' ? 'Lying on' : r.pose === 'sit' ? 'Sitting on' : 'Using'} the ${r.poseName}`
              : r.stuck > 0.3 ? `Can't get through here: ${r.walk.name} needs at least ${(r.walk.width || 20) - SQUEEZE_IN} in to squeeze past`
              : r.tight ? `Tight squeeze${room ? ` in the ${room}` : ''}: less than ${r.walk.width} in here`
                : room ? `In the ${room}` : '' })
        }
      } else if (r) {
        const pts = r.walk.pts
        if (r.pause > 0) r.pause -= dt
        else {
          const before = r.i
          r.i += dt * (speedRef.current / cell)
          // reached the next place in their day: stop for a moment
          // a new leg starts here, so they've just arrived where the previous leg was going: do that activity
          const k2 = r.walk.marks.findIndex((m, j) => j > (r.lastStop ?? 0) && m.at > 0 && m.at > before && m.at <= r.i)
          if (k2 > 0) {
            r.lastStop = k2
            const done = r.walk.marks[k2 - 1]
            const p = pts[Math.max(0, r.walk.marks[k2].at - 1)]
            r.i = r.walk.marks[k2].at - 1
            // a trip they couldn't make: they stop at the narrow door, they don't use anything there
            r.use = /can\u2019t get there|can't get there/.test(done.label) ? null : pickUse(p[0] + 0.5, p[1] + 0.5, done.label, 9)
            r.useLabel = done.label
            r.pause = PAUSE_S + (r.use ? 1.5 : 0)
          }
        }
        if (r.pause <= 0) { r.use = null; r.useLabel = null }
        if (r.i >= pts.length - 1) { endRide(); }
        else {
          const i = Math.floor(r.i), f = r.i - i
          const a = pts[i], b = pts[Math.min(pts.length - 1, i + 1)]
          const x = a[0] + (b[0] - a[0]) * f + 0.5, z = a[1] + (b[1] - a[1]) * f + 0.5
          camera.position.set(x, r.eye, z)
          // heading = average direction over the next few steps, turned smoothly like a head
          let dx = 0, dz = 0
          for (let j = 1; j <= 14; j++) {
            const q = pts[Math.min(pts.length - 1, i + j)]
            dx += q[0] - a[0]; dz += q[1] - a[1]
          }
          if (r.use) turnTo(r, r.use.x, r.use.z, [x, z], dt, 2.5)      // turn to what they use at this stop
          else if (dx || dz) {
            const want = Math.atan2(dz, dx)
            let d = want - r.yaw
            d = Math.atan2(Math.sin(d), Math.cos(d))
            r.yaw += d * Math.min(1, dt * 3)
          }
          // keep the eye toward the middle of the space, the way a person doesn't press against a wall
          const px = -Math.sin(r.yaw), pz = Math.cos(r.yaw)
          const reach = (s) => {
            for (let k = 1; k <= 5; k++) {
              const v = gridRef.current[Math.floor(z + pz * s * k)]?.[Math.floor(x + px * s * k)]
              if (v === undefined || v < 0) return k
            }
            return 5
          }
          const want = Math.max(-1.5, Math.min(1.5, (reach(1) - reach(-1)) / 2))
          r.off += (want - r.off) * Math.min(1, dt * 2)
          // don't stare at a wall from an inch away: if the wall ahead is close, step back (if there's room behind)
          const fx = Math.cos(r.yaw), fz = Math.sin(r.yaw)
          const ray = (s, max) => {
            for (let k = 1; k <= max; k++) {
              const v = gridRef.current[Math.floor(z + fz * s * k * 0.5)]?.[Math.floor(x + fx * s * k * 0.5)]
              if (v === undefined || v < 0) return (k - 1) * 0.5
            }
            return max * 0.5
          }
          const ahead = ray(1, 8), behind = ray(-1, 8)
          const wantBack = ahead < 3 ? Math.min(3 - ahead, Math.max(0, behind - 0.5)) : 0
          r.back = (r.back || 0) + (wantBack - (r.back || 0)) * Math.min(1, dt * 2)
          const ex = x + px * r.off - fx * r.back, ez = z + pz * r.off - fz * r.back
          const pose = r.use ? (r.use.act === 'lie' || r.use.act === 'sit' ? r.use.act : r.use.act === 'watch' ? 'sit' : null) : null
          r.eyeNow = (r.eyeNow ?? r.eye) + (poseEye(r, pose) - (r.eyeNow ?? r.eye)) * Math.min(1, dt * 2.5)
          camera.position.set(ex, r.eyeNow, ez)
          if (!drag.on) {
            r.lookYaw = (r.lookYaw || 0) * Math.max(0, 1 - dt * 0.8)
            r.pitch = (r.pitch || 0) * Math.max(0, 1 - dt * 0.8)
          }
          const ly = r.yaw + (r.lookYaw || 0)
          look.set(ex + Math.cos(ly) * 10, r.eyeNow * 0.97 + Math.tan((r.pitch || 0) + (pose === 'lie' ? 0.25 : 0)) * 10, ez + Math.sin(ly) * 10)
          camera.lookAt(look)
          if (now - hudAt > 110) {
            hudAt = now
            const m = r.useLabel ? { label: r.useLabel } : [...r.walk.marks].reverse().find((k) => k.at <= r.i)
            const doing = r.use ? ` · ${{ lie: 'lies on', sit: 'sits on', watch: 'sits and watches', use: 'uses' }[r.use.act]} the ${r.use.name}` : ''
            setHud({ name: r.walk.name, note: (m?.label || '') + doing, pct: Math.round((r.i / pts.length) * 100), x: ex, z: ez, yaw: ly })
          }
        }
      } else {
        controls.update()
        look.copy(controls.target)
      }
      if (r) {
        for (const g of groups.items.children) {
          const dx = g.position.x - camera.position.x, dz = g.position.z - camera.position.z
          g.visible = dx * dx + dz * dz > (r.pose || r.use ? 1.2 : 2.2) ** 2 || g.position.y > (r.eyeNow ?? r.eye)
        }
      }
      if (aoOn.current) composer.render()
      else renderer.render(scene, camera)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    three.current = { renderer, scene, camera, controls, groups, rows, cols, hemi, sun }
    dollhouse()
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      controls.dispose()
      composer.dispose()
      pmrem.dispose()
      renderer.dispose()
      el.removeChild(renderer.domElement)
      three.current = null
      ride.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [space.id])

  // ---- floor (materials by room, or room colors) and walls
  useEffect(() => {
    const t = three.current
    if (!t) return
    clear(t.groups.floor)
    clear(t.groups.walls)
    const { rows, cols } = t
    const names = Object.fromEntries((rooms || []).map((r) => [r.id, r.name || '']))
    const k = lived ? 16 : 8
    const cv = document.createElement('canvas')
    cv.width = cols * k
    cv.height = rows * k
    const ctx = cv.getContext('2d')
    ctx.fillStyle = '#efece5'
    ctx.fillRect(0, 0, cv.width, cv.height)
    if (showPlan && planImage && !lived) {
      const cellPx = space.px_per_ft * space.cell_in / 12
      const scale = (k / cellPx) * (space.image_size[0] / planImage.naturalWidth)
      ctx.globalAlpha = 0.85
      ctx.drawImage(planImage, 0, 0, planImage.naturalWidth * scale, planImage.naturalHeight * scale)
    }
    // seamless floor patterns, anchored to the whole floor so planks and tiles run on across cells
    const pats = lived ? floorPatterns(ctx, k, cell) : null
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const v = grid[r][c]
        if (v < 0) continue
        const x = c * k, y = r * k
        if (lived) {
          const n = names[v] || ''
          ctx.fillStyle = TILE.test(n) ? pats.tile : DECK.test(n) ? pats.deck : pats.wood
          ctx.fillRect(x, y, k, k)
        } else {
          ctx.globalAlpha = showPlan ? 0.45 : 0.9
          ctx.fillStyle = roomColor(v)
          ctx.fillRect(x, y, k, k)
          ctx.globalAlpha = 1
        }
      }
    }
    ctx.globalAlpha = 1
    const tex = new THREE.CanvasTexture(cv)
    tex.colorSpace = THREE.SRGBColorSpace
    tex.anisotropy = 16
    tex.generateMipmaps = true
    tex.minFilter = THREE.LinearMipmapLinearFilter
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(cols, rows),
      new THREE.MeshStandardMaterial({ map: tex, roughness: lived ? 0.55 : 0.95 }))
    floor.rotation.x = -Math.PI / 2
    floor.position.set(cols / 2, 0, rows / 2)
    floor.receiveShadow = true
    t.groups.floor.add(floor)

    // solid blobs (closets, shafts, filled shapes) are not walls: real walls are thin.
    // a wall cell inside a 5x5 all-wall square, and the cells around it, become a low built-in block
    const W = CODES.WALL
    const isW = (r, c) => r >= 0 && c >= 0 && r < rows && c < cols && grid[r][c] === W
    const core = grid.map((row, r) => row.map((v, c) => {
      if (v !== W) return false
      for (let i = -2; i <= 2; i++) for (let j = -2; j <= 2; j++) if (!isW(r + i, c + j)) return false
      return true
    }))
    const blob = grid.map((row, r) => row.map((v, c) => {
      if (v !== W) return false
      for (let i = -2; i <= 2; i++) for (let j = -2; j <= 2; j++) if (core[r + i]?.[c + j]) return true
      return false
    }))
    // outside walls (wall cells within 3 cells of the outside) get windows when walls are full height
    const O = CODES.OUTSIDE
    const facade = grid.map((row) => row.map(() => false))
    let wave = []
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      if (grid[r][c] !== W || blob[r][c]) continue
      const ns = grid[r + 1]?.[c] === O || grid[r - 1]?.[c] === O
      const ew = grid[r]?.[c + 1] === O || grid[r]?.[c - 1] === O
      if (ns || ew) { facade[r][c] = ns ? 'c' : 'r'; wave.push([r, c]) }
    }
    for (let step = 0; step < 3; step++) {
      const next = []
      for (const [r, c] of wave) for (const [i, j] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const a = r + i, b = c + j
        if (isW(a, b) && !blob[a][b] && !facade[a][b]) { facade[a][b] = facade[r][c]; next.push([a, b]) }
      }
      wave = next
    }
    // windows like a real home: per room and per outside wall, one window centred (two on a long
    // living-room wall); small in baths and kitchens; none in closets, halls or built-ins
    const roomName = Object.fromEntries((rooms || []).map((q) => [q.id, (q.name || '').toLowerCase()]))
    const group = grid.map((row) => row.map(() => null))
    const span = {}
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const ax = facade[r][c]
      if (!ax) continue
      let room = null
      for (let k = 1; k <= 8 && room === null; k++) for (const sgn of [1, -1]) {
        const v = ax === 'c' ? grid[r + sgn * k]?.[c] : grid[r]?.[c + sgn * k]
        if (v >= 0 && room === null) room = v
      }
      if (room === null) continue
      const key = `${room}|${ax}|${Math.round((ax === 'c' ? r : c) / 8)}`
      group[r][c] = key
      const along = ax === 'c' ? c : r
      const g = (span[key] ||= { room, min: along, max: along })
      g.min = Math.min(g.min, along); g.max = Math.max(g.max, along)
    }
    const openings = {}
    for (const [key, g] of Object.entries(span)) {
      const n = roomName[g.room] || ''
      const len = g.max - g.min + 1
      if (/closet|cl\b|hall|built|storage|pantry|laundry|utility|foyer|entry/.test(n) || len < 10) { openings[key] = []; continue }
      const w = /bath|wc|toilet|powder|kitchen/.test(n) ? 5 : Math.min(10, Math.floor(len * 0.4))
      const mid = (g.min + g.max) / 2
      openings[key] = len >= 40 && /living|family|great|lounge|dining/.test(n)
        ? [[mid - len * 0.25 - w / 2, mid - len * 0.25 + w / 2], [mid + len * 0.25 - w / 2, mid + len * 0.25 + w / 2]]
        : [[mid - w / 2, mid + w / 2]]
    }
    const windowAt = (r, c) => {
      const key = group[r][c]
      if (!key) return false
      const along = facade[r][c] === 'c' ? c : r
      return openings[key].some(([a, b]) => along >= a && along < b)
    }
    const code = (r, c) => (blob[r][c] ? 'BLOB' : facade[r][c] && tall && lived && windowAt(r, c) ? 'FACADE' : grid[r][c])
    const runs = (want) => {
      const out = []
      for (let r = 0; r < rows; r++) {
        let c = 0
        while (c < cols) {
          if (code(r, c) !== want) { c++; continue }
          const s = c
          while (c < cols && code(r, c) === want) c++
          out.push([r, s, c - s])
        }
      }
      return out
    }
    const box = new THREE.BoxGeometry(1, 1, 1)
    const wallIn = tall ? WALL_IN : CUTAWAY_IN
    const fixColor = lived ? 0xd9c3a0 : 0xb9b6ad     // built-ins drawn on the plan: counters, desks, tables
    const wallColor = lived ? 0xeee4d3 : 0xf4f1ea
    const addRuns = (list, y0In, y1In, material, shadow = true, grow = 1) => {
      if (!list.length) return
      const y0 = y0In / cell, h = (y1In - y0In) / cell
      const mesh = new THREE.InstancedMesh(box, material, list.length)
      const m = new THREE.Matrix4()
      list.forEach(([r, c, n], i) => {
        m.compose(new THREE.Vector3(c + n / 2, y0 + h / 2, r + 0.5), new THREE.Quaternion(), new THREE.Vector3(n * grow, h, grow))
        mesh.setMatrixAt(i, m)
      })
      mesh.castShadow = shadow
      mesh.receiveShadow = true
      t.groups.walls.add(mesh)
    }
    const solid = (color) => new THREE.MeshStandardMaterial({ color, roughness: 0.85 })
    const walls = runs(CODES.WALL)
    addRuns(walls, 0, wallIn, solid(wallColor))
    addRuns(runs(CODES.FIXTURE), 0, FIXTURE_IN, solid(fixColor))
    addRuns(runs('BLOB'), 0, lived ? FIXTURE_IN : wallIn, solid(lived ? 0xd9d3c7 : 0xf4f1ea))
    const facadeRuns = runs('FACADE')
    if (facadeRuns.length) {
      // sill wall, window glass with a frame band, and the wall above
      addRuns(facadeRuns, 0, 30, solid(wallColor))
      addRuns(facadeRuns, 30, 32, solid(0xffffff))
      addRuns(facadeRuns, 32, 82, new THREE.MeshStandardMaterial({ color: 0xcfe6f5, roughness: 0.05, metalness: 0.1,
        transparent: true, opacity: 0.28, emissive: 0x9fc9e8, emissiveIntensity: 0.25 }), false)
      addRuns(facadeRuns, 82, 84, solid(0xffffff))
      addRuns(facadeRuns, 84, WALL_IN, solid(wallColor))
    }
    if (lived) {
      // white baseboards along every wall, a little proud of the wall face
      addRuns([...walls, ...facadeRuns], 0, 4, solid(0xfbfaf7), false, 1.08)
      // door frames: short floor gaps between walls, with room on both sides
      {
        const frames = []
        const isWall = (r, c) => { const v = grid[r]?.[c]; return v === W || v === CODES.FIXTURE }
        const open = (r, c) => { const v = grid[r]?.[c]; return v !== undefined && v >= 0 }
        for (let r = 4; r < rows - 4; r++) {
          let c = 0
          while (c < cols) {
            if (!open(r, c)) { c++; continue }
            const s0 = c
            while (c < cols && open(r, c)) c++
            const n = c - s0
            if (n >= 3 && n <= 8 && isWall(r, s0 - 1) && isWall(r, c) && open(r - 4, s0) && open(r + 4, s0)
              && open(r - 4, c - 1) && open(r + 4, c - 1) && !(open(r - 4, s0 - 1) && open(r + 4, s0 - 1) && open(r, s0 - 3))) {
              frames.push({ x: s0 + n / 2, z: r + 0.5, w: n, d: 1, along: 'x' })
            }
          }
        }
        for (let c = 4; c < cols - 4; c++) {
          let r = 0
          while (r < rows) {
            if (!open(r, c)) { r++; continue }
            const s0 = r
            while (r < rows && open(r, c)) r++
            const n = r - s0
            if (n >= 3 && n <= 8 && isWall(s0 - 1, c) && isWall(r, c) && open(s0, c - 4) && open(s0, c + 4)
              && open(r - 1, c - 4) && open(r - 1, c + 4)) {
              frames.push({ x: c + 0.5, z: s0 + n / 2, w: 1, d: n, along: 'z' })
            }
          }
        }
        // merge frames from neighbouring rows of the same thick-wall doorway: keep one per spot
        const kept = []
        for (const f of frames) if (!kept.some((k) => Math.abs(k.x - f.x) < 2 && Math.abs(k.z - f.z) < 2)) kept.push(f)
        const trim = solid(0xffffff)
        const head = 80 / cell, top = WALL_IN / cell
        if (tall) for (const f of kept) {
          const lintel = new THREE.Mesh(box, solid(wallColor))
          lintel.scale.set(f.w, top - head, f.d)
          lintel.position.set(f.x, head + (top - head) / 2, f.z)
          t.groups.walls.add(lintel)
          const bar = new THREE.Mesh(box, trim)
          bar.scale.set(f.along === 'x' ? f.w : 1.15, 0.35, f.along === 'z' ? f.d : 1.15)
          bar.position.set(f.x, head + 0.17, f.z)
          t.groups.walls.add(bar)
          for (const s of [-1, 1]) {
            const post = new THREE.Mesh(box, trim)
            post.scale.set(f.along === 'x' ? 0.35 : 1.15, head, f.along === 'z' ? 0.35 : 1.15)
            post.position.set(f.along === 'x' ? f.x + s * (f.w / 2 - 0.17) : f.x, head / 2, f.along === 'z' ? f.z + s * (f.d / 2 - 0.17) : f.z)
            t.groups.walls.add(post)
          }
        }
        // real doors where SAM 3.1 found them: hinged at one side of the doorway, standing open
        // toward the side the swing is drawn on
        const leafMat = new THREE.MeshStandardMaterial({ color: 0xe9dcc4, roughness: 0.6 })
        const knobMat = new THREE.MeshStandardMaterial({ color: 0xb8bcc0, roughness: 0.3, metalness: 0.7 })
        const leafH = Math.min(80, tall ? 80 : CUTAWAY_IN + 6) / cell
        for (const d of (space.doors || []).filter((x) => x.has_door !== false)) {
          // the door finder gives the opening's middle, which way the wall runs, and the width
          const len = (d.width_in / cell) * 0.96
          const along = d.axis || 'x'                 // 'x': the opening runs along x, so the wall does too
          // swing into the room side: look a few cells each way for floor that isn't outside
          const probe = (sgn) => { for (let k = 2; k <= 6; k++) {
            const r = Math.floor(along === 'x' ? d.y + sgn * k : d.y), c = Math.floor(along === 'x' ? d.x : d.x + sgn * k)
            const v = grid[r]?.[c]; if (v !== undefined && v >= 0) return true } return false }
          const side = probe(1) ? 1 : -1
          const leaf = new THREE.Mesh(box, leafMat)
          const knob = new THREE.Mesh(new THREE.SphereGeometry(0.22, 12, 8), knobMat)
          if (along === 'x') {           // open leaf stands along z, hinged at the opening's left end
            const hx = d.x - len / 2 + 0.2
            leaf.scale.set(0.28, leafH, len)
            leaf.position.set(hx, leafH / 2, d.y + side * len / 2)
            knob.position.set(hx + 0.3, 36 / cell, d.y + side * (len - 0.5))
          } else {
            const hz = d.y - len / 2 + 0.2
            leaf.scale.set(len, leafH, 0.28)
            leaf.position.set(d.x + side * len / 2, leafH / 2, hz)
            knob.position.set(d.x + side * (len - 0.5), 36 / cell, hz + 0.3)
          }
          leaf.castShadow = true
          t.groups.walls.add(leaf, knob)
        }
      }
      // even indoor light so walls don't go brown, then a soft warm light in each room
      const amb = new THREE.AmbientLight(0xfff8ee, rider ? 1.1 : 0.5)
      amb.userData.day = amb.intensity
      t.groups.walls.add(amb)
      const sums = {}
      for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
        const v = grid[r][c]
        if (v < 0) continue
        const a = (sums[v] ||= [0, 0, 0]); a[0] += c; a[1] += r; a[2]++
      }
      for (const [, [sc, sr, n]] of Object.entries(sums)) {
        if (n < 60) continue
        const light = new THREE.PointLight(0xffd9a8, 0.9, 60, 1.2)
        light.position.set(sc / n, 84 / cell, sr / n)
        light.userData.day = light.intensity
        t.groups.walls.add(light)
      }
    }
    // a ceiling, only when walking through in first person
    if (rider) {
      const ceil = new THREE.Mesh(new THREE.PlaneGeometry(cols, rows), new THREE.MeshStandardMaterial({ color: 0xf7f4ee, emissive: 0xfff6e8, emissiveIntensity: 0.55, side: THREE.DoubleSide }))
      ceil.rotation.x = Math.PI / 2
      ceil.position.set(cols / 2, WALL_IN / cell, rows / 2)
      ceil.userData.ceiling = true
      t.groups.walls.add(ceil)
    }
  }, [grid, rooms, showPlan, planImage, space, cell, tall, lived, rider])

  // ---- night: house lights off, a little moonlight, night lights glow (they're added with the furniture)
  useEffect(() => {
    const t = three.current
    if (!t) return
    t.hemi.intensity = night ? 0.12 : 1.0
    t.scene.environmentIntensity = night ? 0.03 : 0.55
    t.hemi.color.set(night ? 0x8fa6d6 : 0xfff6e8)
    t.sun.intensity = night ? 0.15 : 1.6
    t.sun.color.set(night ? 0x9fb4e6 : 0xfff2dd)
    t.groups.walls.traverse((o) => {
      if (o.isLight && o.userData.day != null) o.intensity = night ? o.userData.day * (o.isAmbientLight ? 0.12 : 0.03) : o.userData.day
      if (o.userData.ceiling) o.material.emissiveIntensity = night ? 0.02 : 0.55
    })
    const card = getComputedStyle(document.documentElement).getPropertyValue('--card').trim() || '#ffffff'
    t.scene.background = new THREE.Color(night ? 0x0b1020 : rider ? 0xdfe9f2 : card)
  }, [night, rider, grid, rooms, lived, showPlan, tall])

  // ---- furniture: real shapes in lived-in mode, boxes otherwise
  useEffect(() => {
    const t = three.current
    if (!t) return
    clear(t.groups.items)
    const cats = Object.fromEntries(catalog.map((c) => [c.id, c]))
    const extra = lived && typical && catalog.length
      ? typicalFurniture(grid, rooms, items.filter((i) => i.status !== 'removed' && i.status !== 'replaced'), catalog, cell, walks) : []
    for (const it of extra) t.groups.items.add(buildItem(it, cats[it.item], cell, it.facing))
    // furniture you can't walk through when walking as someone (not rugs or wall things)
    const solid = grid.map((row) => row.map(() => false))
    for (const it of [...extra, ...items.filter((i) => i.status !== 'removed' && i.status !== 'replaced')]) {
      const c = cats[it.item]
      if (!c || !c.size_in.h || c.size_in.d < 6 || c.category === 'safety') continue
      for (let r = Math.round(it.y - it.d / 2); r < Math.round(it.y + it.d / 2); r++)
        for (let q = Math.round(it.x - it.w / 2); q < Math.round(it.x + it.w / 2); q++) if (solid[r]) solid[r][q] = true
    }
    solidRef.current = solid
    usable.current = [...extra, ...items.filter((i) => i.status !== 'removed' && i.status !== 'replaced')]
      .map((it) => ({ x: it.x, z: it.y, w: it.w, d: it.d, act: actionFor(it.item), kind: kindOf(it.item),
        name: cats[it.item]?.name || it.name || it.item }))
      .filter((u) => u.act)
    for (const it of items) {
      const gone = it.status === 'removed' || it.status === 'replaced'
      if (lived && !gone) {
        const g = buildItem(it, cats[it.item], cell, facingFor(it, grid))
        if (it.status === 'new') {
          const ring = new THREE.Mesh(new THREE.RingGeometry(Math.max(it.w, it.d) * 0.55, Math.max(it.w, it.d) * 0.55 + 0.35, 40),
            new THREE.MeshBasicMaterial({ color: STATUS_COLOR.new, transparent: true, opacity: 0.8 }))
          ring.rotation.x = -Math.PI / 2
          ring.position.set(it.x, 0.05, it.y)
          t.groups.items.add(ring)
        }
        t.groups.items.add(g)
        if (night && /night-light|stick-lights|led-under-cabinet|lamp/.test(it.item || '')) {
          const glow = new THREE.PointLight(0xffc27a, 2.2, 30, 1.6)
          glow.position.set(it.x, 1.2, it.y)
          t.groups.items.add(glow)
        }
        continue
      }
      const hIn = cats[it.item]?.size_in?.h ?? 30
      const flat = hIn === 0
      const wallMounted = !flat && it.w <= 1.01 && it.d <= 1.01
      const h = flat ? 0.15 : wallMounted ? 0.8 : hIn / cell
      const color = STATUS_COLOR[it.status] ?? STATUS_COLOR.kept
      const mat = new THREE.MeshStandardMaterial({ color, roughness: 0.6, transparent: gone, opacity: gone ? 0.3 : 1 })
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(Math.max(0.6, it.w), h, Math.max(0.6, it.d)), mat)
      const y = wallMounted ? (it.item === 'smoke-alarm' || it.item === 'ceiling-fan' || it.item?.startsWith('pendant')
        ? WALL_IN / cell - 0.6 : 6) : h / 2
      mesh.position.set(it.x, y, it.y)
      mesh.castShadow = !gone
      t.groups.items.add(mesh)
    }
  }, [items, catalog, cell, lived, grid, rooms, typical, walks, night, models])

  // ---- people where they are now, with their trail (hidden while riding along)
  useEffect(() => {
    const t = three.current
    if (!t) return
    clear(t.groups.people)
    if (rider) return
    const h = PERSON_IN / cell
    for (const p of people) {
      if (!p.at) continue
      const color = new THREE.Color(p.color)
      const body = new THREE.Mesh(new THREE.CapsuleGeometry(1.2, h - 3.6, 4, 12),
        new THREE.MeshStandardMaterial({ color, roughness: 0.5 }))
      body.position.set(p.at[0] + 0.5, h / 2, p.at[1] + 0.5)
      body.castShadow = true
      t.groups.people.add(body)
      if (p.trail?.length > 1) {
        const pts = p.trail.map(([c, r]) => new THREE.Vector3(c + 0.5, 0.2, r + 0.5))
        t.groups.people.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
          new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.7 })))
      }
    }
  }, [people, cell, rider])

  // ---- an item being carried in
  useEffect(() => {
    const t = three.current
    if (!t) return
    clear(t.groups.ghost)
    if (!ghost) return
    const tone = { carry: 0x2f7fd6, bad: 0xc0392b, ok: 0x2f9e6b }[ghost.tone] ?? 0x2f7fd6
    const box = new THREE.Mesh(new THREE.BoxGeometry(Math.max(0.8, ghost.w), 5, Math.max(0.8, ghost.d)),
      new THREE.MeshStandardMaterial({ color: tone, transparent: true, opacity: 0.55 }))
    box.position.set(ghost.x, 2.5, ghost.y)
    t.groups.ghost.add(box)
    if (ghost.trail?.length > 1) {
      const pts = ghost.trail.map(([c, r]) => new THREE.Vector3(c + 0.5, 0.25, r + 0.5))
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
        new THREE.LineDashedMaterial({ color: 0x2f7fd6, dashSize: 1.5, gapSize: 1 }))
      line.computeLineDistances()
      t.groups.ghost.add(line)
    }
  }, [ghost])

  useEffect(() => {
    if (three.current) three.current.controls.autoRotate = orbit && !rider
  }, [orbit, rider])

  // stop riding if the person disappears (new run, Before/After switch)
  useEffect(() => {
    if (rider && !walks.some((w) => w.id === rider)) endRide()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [walks, rider])

  useEffect(() => {
    if (!driving) return
    const move = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'w', 'a', 's', 'd'])
    // e: sit, lie down, use, or stand up again
    const down = (e) => {
      const k = e.key.length === 1 ? e.key.toLowerCase() : e.key
      if (e.target.closest?.('input, textarea')) return
      if (move.has(k)) {
        keys.current[k] = true
        if (!e.repeat) keys.current['until_' + k] = performance.now() + 180   // a quick tap still takes a small step
        e.preventDefault()
      }
      if (k === 'Escape') endRide()
      if (k === 'e') {
        const r = ride.current
        if (!r) return
        if (r.pose) { r.pose = null; r.x = r.standX; r.z = r.standZ; return }
        const u = r.near
        if (!u) return
        r.standX = r.x; r.standZ = r.z
        r.poseName = u.name
        if (u.act === 'sit' || u.act === 'lie') {
          // sit or lie on it, looking back out into the room
          r.yaw = Math.atan2(r.z - u.z, r.x - u.x)
          r.x = u.x + (r.x - u.x) * 0.25; r.z = u.z + (r.z - u.z) * 0.25
          r.pose = u.act
        } else {
          r.yaw = Math.atan2(u.z - r.z, u.x - r.x)
          r.pose = 'use'
        }
      }
    }
    const up = (e) => {
      const k = e.key.length === 1 ? e.key.toLowerCase() : e.key
      const wait = (keys.current['until_' + k] || 0) - performance.now()
      if (wait > 0) setTimeout(() => { keys.current[k] = false }, wait)
      else keys.current[k] = false
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [driving])

  const hold = (k) => ({
    onPointerDown: (e) => { e.preventDefault(); keys.current[k] = true },
    onPointerUp: () => { keys.current[k] = false },
    onPointerLeave: () => { keys.current[k] = false },
  })

  function startRide(walk, record = false, drive = false) {
    const t = three.current
    if (!t || !walk?.pts?.length) return
    const eye = eyeIn(walk) / cell
    const p0 = walk.pts[0], p1 = walk.pts[Math.min(walk.pts.length - 1, 10)]
    // body width in cells, measured the same way the day was: a square that wide must fit
    const halfOf = (inches) => Math.max(0.4, inches / cell / 2 - 0.5)
    const half = halfOf((walk.width || 20) - SQUEEZE_IN)      // can pass (same rule as the measured day)
    const comfy = halfOf(walk.width || 20)                     // passes without squeezing
    // at night, ride along from their night trip (the 2 AM bathroom walk), not from the morning
    const nk = night && !drive ? walk.marks.findIndex((m) => m.at > 0 && m.at < walk.pts.length - 5 && /night|^0[0-4]:/i.test(m.label || '')) : -1
    if (nk > 0) {
      const at = walk.marks[nk].at
      const a = walk.pts[at] || p0, b = walk.pts[Math.min(walk.pts.length - 1, at + 10)]
      ride.current = { walk, i: at, lastStop: nk, eye, off: 0, yaw: Math.atan2(b[1] - a[1], b[0] - a[0]),
        drive, x: a[0] + 0.5, z: a[1] + 0.5, half, comfy }
    } else
    ride.current = { walk, i: 0, eye, off: 0, yaw: Math.atan2(p1[1] - p0[1], p1[0] - p0[0]),
      drive, x: p0[0] + 0.5, z: p0[1] + 0.5, half, comfy }
    keys.current = {}
    setDriving(drive)
    t.controls.enabled = false
    t.bg = t.scene.background
    t.scene.background = new THREE.Color(0xdfe9f2)   // a light sky over the open-top rooms
    t.camera.fov = 75
    t.camera.updateProjectionMatrix()
    setRider(walk.id)
    // keep the whole 3D view on screen, just under the top bar
    const top = mount.current ? mount.current.getBoundingClientRect().top + window.scrollY - 70 : null
    if (top != null) window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
    if (record) startRecording(walk.name)
  }

  function endRide() {
    const t = three.current
    ride.current = null
    keys.current = {}
    setDriving(false)
    setRider(null)
    setHud(null)
    stopRecording()
    if (!t) return
    t.controls.enabled = true
    if (t.bg) t.scene.background = t.bg
    t.camera.fov = 40
    t.camera.updateProjectionMatrix()
    dollhouse()
  }

  function startRecording(name) {
    const t = three.current
    if (!t || typeof MediaRecorder === 'undefined') return
    const stream = t.renderer.domElement.captureStream(30)
    const type = ['video/webm;codecs=vp9', 'video/webm'].find((m) => MediaRecorder.isTypeSupported(m)) || ''
    const rec = new MediaRecorder(stream, type ? { mimeType: type, videoBitsPerSecond: 6e6 } : undefined)
    const chunks = []
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data)
    rec.onstop = () => {
      const url = URL.createObjectURL(new Blob(chunks, { type: 'video/webm' }))
      const a = document.createElement('a')
      a.href = url
      a.download = `lifespace-${(name || 'walk').toLowerCase()}-day.webm`
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 5000)
    }
    rec.start()
    t.recorder = rec
    setRecording(true)
  }

  function stopRecording() {
    const t = three.current
    if (t?.recorder && t.recorder.state !== 'inactive') t.recorder.stop()
    if (t) t.recorder = null
    setRecording(false)
  }

  function dollhouse() {
    const t = three.current
    if (!t || ride.current) return
    const span = Math.max(t.cols, t.rows)
    t.camera.position.set(t.cols * 0.5, span * 0.72, t.rows * 1.12)
    t.controls.target.set(t.cols / 2, 0, t.rows / 2)
    t.controls.update()
  }

  function topDown() {
    const t = three.current
    if (!t || ride.current) return
    t.camera.position.set(t.cols / 2, Math.max(t.cols, t.rows) * 1.25, t.rows / 2 + 0.01)
    t.controls.target.set(t.cols / 2, 0, t.rows / 2)
    t.controls.update()
  }

  const riding = walks.find((w) => w.id === rider)

  return (
    <div className="view3d">
      <div className="view3d-stage">
        <div ref={mount} className="view3d-canvas" />
        {riding && hud && (
          <MiniMap grid={grid} x={hud.x} z={hud.z} yaw={hud.yaw} color={riding.color} path={driving ? [] : riding.pts} />
        )}
        {riding && hud && (
          <div className="fp-hud">
            <strong style={{ color: riding.color }}>● {hud.name}&apos;s eyes</strong>
            <span>{hud.note}</span>
            {hud.near && <strong className="fp-near">{hud.near}</strong>}
            {hud.drive ? <em className="fp-help">Arrows or W A S D to walk · E to sit or lie down · drag to look around · {riding.width} in wide · Esc to stop</em>
              : <div className="fp-bar"><i style={{ width: `${hud.pct}%`, background: riding.color }} /></div>}
            {recording && <em className="rec">● REC</em>}
          </div>
        )}
      </div>
      <div className="view3d-tools">
        {rider ? (
          <>
            <button className="tool on" onClick={endRide}>{recording ? 'Stop and save video' : 'Exit first person'}</button>
            {driving && (
              <span className="pad">
                <button className="tool" {...hold('ArrowLeft')} aria-label="Turn left">◀</button>
                <button className="tool" {...hold('ArrowUp')} aria-label="Walk forward">▲</button>
                <button className="tool" {...hold('ArrowDown')} aria-label="Step back">▼</button>
                <button className="tool" {...hold('ArrowRight')} aria-label="Turn right">▶</button>
                <button className="tool" onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'e' }))}
                  aria-label="Sit, lie down or stand up">E</button>
              </span>
            )}
            {!driving && Object.keys(SPEEDS).map((k) => (
              <button key={k} className={speed === k ? 'tool on' : 'tool'} onClick={() => setSpeed(k)}>{k}</button>
            ))}
            {!driving && <span className="meta">Stops at each place in their day · drag to look around</span>}
          </>
        ) : (
          <>
            <button className={lived ? 'tool on' : 'tool'} onClick={() => setLived((l) => !l)}>Lived-in</button>
            {lived && <button className={typical ? 'tool on' : 'tool'} onClick={() => setTypical((v) => !v)}
              title="Beds, sofas and tables a room obviously has. Picture only: not on your plan, not in the scores">Typical furniture</button>}
            <button className="tool" onClick={dollhouse}>Dollhouse</button>
            <button className="tool" onClick={topDown}>Top down</button>
            <button className={orbit ? 'tool on' : 'tool'} onClick={() => setOrbit((o) => !o)}>Slow orbit</button>
            <button className={fullWalls ? 'tool on' : 'tool'} onClick={() => setFullWalls((f) => !f)}>Full walls</button>
            <button className={night ? 'tool on' : 'tool'} onClick={() => setNight((n) => !n)}
              title="2 AM: house lights off, only night lights glow. Ride along starts at the night trip">Night</button>
            <button className={ao ? 'tool on' : 'tool'} onClick={() => setAo((v) => !v)}
              title="Soft shadows in corners and under furniture. Turn off if the 3D view feels slow">Soft shadows</button>
          </>
        )}
      </div>
      {walks.length > 0 && !rider && (
        <div className="view3d-tools fp-pick">
          <span className="meta">See their day through their eyes:</span>
          {walks.map((w) => (
            <span key={w.id} className="fp-person">
              <button className="tool" onClick={() => startRide(w)} style={{ borderColor: w.color }}>
                <span style={{ color: w.color }}>●</span> {w.name}
              </button>
              <button className="tool" title="Ride along and download a video" onClick={() => startRide(w, true)}>⏺ video</button>
              <button className="tool" title={`Walk as ${w.name} with the arrow keys; you only fit where a ${w.width} in body fits`}
                onClick={() => startRide(w, false, true)}>Walk as</button>
            </span>
          ))}
        </div>
      )}
      {lived && typical && <p className="meta">Rooms are filled with typical furniture for the picture. It isn&apos;t on your plan and isn&apos;t counted in any score; it never sits where someone walks.</p>}
      {!walks.length && <p className="meta">Run a day on the People tab to ride along with someone in first person.</p>}
    </div>
  )
}

// a small seeded random, so the floor looks the same every time
function rng(seed) { let x = seed; return () => ((x = (x * 16807) % 2147483647) / 2147483647) }

/** Wood planks (5 in wide, staggered, with grain), 12 in tiles with grout, and deck boards. */
function floorPatterns(ctx, k, cellIn) {
  const px = k / cellIn                       // canvas pixels per inch
  const make = (w, h, draw) => {
    const c = document.createElement('canvas')
    c.width = Math.round(w); c.height = Math.round(h)
    draw(c.getContext('2d'), c.width, c.height)
    return ctx.createPattern(c, 'repeat')
  }
  const wood = make(96 * px, 5 * px * 8, (g, w, h) => {
    const rand = rng(7)
    const ph = h / 8
    for (let i = 0; i < 8; i++) {
      const off = (i * 37 % 8) / 8 * w
      for (const start of [off - w, off]) {
        const tone = 190 + Math.floor(rand() * 22)
        g.fillStyle = `rgb(${tone}, ${Math.round(tone * 0.76)}, ${Math.round(tone * 0.52)})`
        g.fillRect(start, i * ph, w, ph)
        g.globalAlpha = 0.08
        g.fillStyle = '#5a3d22'
        for (let s = 0; s < 6; s++) g.fillRect(start, i * ph + rand() * ph, w, 0.6)   // grain
        g.globalAlpha = 1
        g.fillStyle = 'rgba(90, 60, 35, 0.45)'
        g.fillRect(start + w - 0.8, i * ph, 0.8, ph)                                     // plank end
      }
      g.fillStyle = 'rgba(90, 60, 35, 0.35)'
      g.fillRect(0, i * ph + ph - 0.8, w, 0.8)                                           // seam
    }
  })
  const tile = make(24 * px, 24 * px, (g, w, h) => {
    const rand = rng(3)
    for (const [x, y] of [[0, 0], [w / 2, 0], [0, h / 2], [w / 2, h / 2]]) {
      const t = 228 + Math.floor(rand() * 10)
      g.fillStyle = `rgb(${t}, ${t + 3}, ${t + 4})`
      g.fillRect(x, y, w / 2, h / 2)
    }
    g.fillStyle = 'rgba(150, 158, 162, 0.7)'
    for (const v of [0, w / 2]) { g.fillRect(v, 0, 1, h); g.fillRect(0, v, w, 1) }
  })
  const deck = make(48 * px, 6 * px * 4, (g, w, h) => {
    const rand = rng(11)
    const bh = h / 4
    for (let i = 0; i < 4; i++) {
      const t = 150 + Math.floor(rand() * 18)
      g.fillStyle = `rgb(${t}, ${Math.round(t * 0.78)}, ${Math.round(t * 0.58)})`
      g.fillRect(0, i * bh, w, bh - 1.5)
      g.fillStyle = 'rgba(60, 40, 25, 0.8)'
      g.fillRect(0, i * bh + bh - 1.5, w, 1.5)
    }
  })
  return { wood, tile, deck }
}

function fitsAtGrid(grid, solid, x, z, half) {
  for (let r = Math.floor(z - half); r <= Math.floor(z + half); r++)
    for (let c = Math.floor(x - half); c <= Math.floor(x + half); c++) {
      const v = grid[r]?.[c]
      if (v === undefined || v < 0 || solid?.[r]?.[c]) return false
    }
  return true
}

function clear(group) {
  for (const child of [...group.children]) {
    group.remove(child)
    child.traverse?.((o) => {
      o.geometry?.dispose?.()
      const m = o.material
      // shared furniture materials are cached in furniture3d, so only free per-mesh ones
      if (m && !m.userData?.shared) {
        if (Array.isArray(m)) m.forEach((x) => x.dispose())
        else { m.map?.dispose?.(); m.dispose?.() }
      }
    })
  }
}
