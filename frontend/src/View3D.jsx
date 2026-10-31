import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { CODES, roomColor } from './mapStyle'
import { buildItem, facingFor } from './furniture3d'

// 1 grid cell = 6 in = 1 unit, so heights in inches divide by the cell size
const WALL_IN = 96          // 8 ft walls
const CUTAWAY_IN = 40       // walls cut at about 3 ft, the way architects show a model
const FIXTURE_IN = 36       // counters, tubs and other built-ins
const PERSON_IN = 66
const WALK_IN_PER_S = 60   // a calm walk, a bit slower than real so the video reads well
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
  const [orbit, setOrbit] = useState(false)
  const [fullWalls, setFullWalls] = useState(false)
  const [lived, setLived] = useState(true)
  const [rider, setRider] = useState(null)        // walk id being ridden
  const [hud, setHud] = useState(null)
  const [recording, setRecording] = useState(false)
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

    scene.add(new THREE.HemisphereLight(0xfff6e8, 0x8a8577, 1.5))
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

    function resize() {
      const w = el.clientWidth, h = Math.max(360, Math.round(w * 0.62))
      renderer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(el)

    let raf, last = performance.now(), hudAt = 0
    const look = new THREE.Vector3()
    const loop = (now) => {
      const dt = Math.min(0.1, (now - last) / 1000)
      last = now
      const r = ride.current
      if (r) {
        r.i += dt * (WALK_IN_PER_S / cell)
        const pts = r.walk.pts
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
          if (dx || dz) {
            const want = Math.atan2(dz, dx)
            let d = want - r.yaw
            d = Math.atan2(Math.sin(d), Math.cos(d))
            r.yaw += d * Math.min(1, dt * 3)
          }
          look.set(x + Math.cos(r.yaw) * 10, r.eye * 0.97, z + Math.sin(r.yaw) * 10)
          camera.lookAt(look)
          if (now - hudAt > 200) {
            hudAt = now
            const m = [...r.walk.marks].reverse().find((k) => k.at <= r.i)
            setHud({ name: r.walk.name, note: m?.label || '', pct: Math.round((r.i / pts.length) * 100) })
          }
        }
      } else {
        controls.update()
        look.copy(controls.target)
      }
      renderer.render(scene, camera)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    three.current = { renderer, scene, camera, controls, groups, rows, cols }
    dollhouse()
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      controls.dispose()
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
    const k = 8
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
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const v = grid[r][c]
        if (v < 0) continue
        const x = c * k, y = r * k
        if (lived) {
          const n = names[v] || ''
          if (TILE.test(n)) {
            ctx.fillStyle = (r >> 1) % 2 === (c >> 1) % 2 ? '#e9ecec' : '#dfe3e4'
            ctx.fillRect(x, y, k, k)
            ctx.fillStyle = '#c9cfd1'
            if (c % 2 === 0) ctx.fillRect(x, y, 1, k)
            if (r % 2 === 0) ctx.fillRect(x, y, k, 1)
          } else if (DECK.test(n)) {
            ctx.fillStyle = r % 2 ? '#9c7b5b' : '#a5835f'
            ctx.fillRect(x, y, k, k)
            ctx.fillStyle = '#6f5640'
            ctx.fillRect(x, y + k - 1, k, 1)
          } else {
            const plank = (r + ((c >> 3) % 2) * 1) % 3
            ctx.fillStyle = ['#c49a6c', '#bb9163', '#c8a174'][plank]
            ctx.fillRect(x, y, k, k)
            ctx.fillStyle = '#9d754e'
            if (r % 1 === 0) ctx.fillRect(x, y + k - 1, k, 1)
            if ((c + r * 3) % 8 === 0) ctx.fillRect(x, y, 1, k)
          }
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
    tex.anisotropy = 8
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
    const code = (r, c) => (blob[r][c] ? 'BLOB' : grid[r][c])
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
    const fixColor = lived ? 0xe6e2da : 0xb9b6ad
    for (const [kind, inches, color] of [[CODES.WALL, wallIn, 0xf4f1ea], [CODES.FIXTURE, FIXTURE_IN, fixColor],
      ['BLOB', lived ? FIXTURE_IN : wallIn, lived ? 0xd9d3c7 : 0xf4f1ea]]) {
      const list = runs(kind)
      if (!list.length) continue
      const h = inches / cell
      const mesh = new THREE.InstancedMesh(box, new THREE.MeshStandardMaterial({ color, roughness: 0.85 }), list.length)
      const m = new THREE.Matrix4()
      list.forEach(([r, c, n], i) => {
        m.compose(new THREE.Vector3(c + n / 2, h / 2, r + 0.5), new THREE.Quaternion(), new THREE.Vector3(n, h, 1))
        mesh.setMatrixAt(i, m)
      })
      mesh.castShadow = true
      mesh.receiveShadow = true
      t.groups.walls.add(mesh)
    }
  }, [grid, rooms, showPlan, planImage, space, cell, tall, lived])

  // ---- furniture: real shapes in lived-in mode, boxes otherwise
  useEffect(() => {
    const t = three.current
    if (!t) return
    clear(t.groups.items)
    const cats = Object.fromEntries(catalog.map((c) => [c.id, c]))
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
  }, [items, catalog, cell, lived, grid])

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

  function startRide(walk, record = false) {
    const t = three.current
    if (!t || !walk?.pts?.length) return
    const eye = eyeIn(walk) / cell
    const p0 = walk.pts[0], p1 = walk.pts[Math.min(walk.pts.length - 1, 10)]
    ride.current = { walk, i: 0, eye, yaw: Math.atan2(p1[1] - p0[1], p1[0] - p0[0]) }
    t.controls.enabled = false
    t.bg = t.scene.background
    t.scene.background = new THREE.Color(0xdfe9f2)   // a light sky over the open-top rooms
    t.camera.fov = 75
    t.camera.updateProjectionMatrix()
    setRider(walk.id)
    if (record) startRecording(walk.name)
  }

  function endRide() {
    const t = three.current
    ride.current = null
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
          <div className="fp-hud">
            <strong style={{ color: riding.color }}>● {hud.name}&apos;s eyes</strong>
            <span>{hud.note}</span>
            <div className="fp-bar"><i style={{ width: `${hud.pct}%`, background: riding.color }} /></div>
            {recording && <em className="rec">● REC</em>}
          </div>
        )}
      </div>
      <div className="view3d-tools">
        {rider ? (
          <button className="tool on" onClick={endRide}>{recording ? 'Stop and save video' : 'Exit first person'}</button>
        ) : (
          <>
            <button className={lived ? 'tool on' : 'tool'} onClick={() => setLived((l) => !l)}>Lived-in</button>
            <button className="tool" onClick={dollhouse}>Dollhouse</button>
            <button className="tool" onClick={topDown}>Top down</button>
            <button className={orbit ? 'tool on' : 'tool'} onClick={() => setOrbit((o) => !o)}>Slow orbit</button>
            <button className={fullWalls ? 'tool on' : 'tool'} onClick={() => setFullWalls((f) => !f)}>Full walls</button>
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
            </span>
          ))}
        </div>
      )}
      {!walks.length && <p className="meta">Run a day on the People tab to ride along with someone in first person.</p>}
    </div>
  )
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
