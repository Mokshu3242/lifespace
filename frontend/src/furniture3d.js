import * as THREE from 'three'

/**
 * Real-looking furniture from simple shapes, scaled exactly to the catalog size.
 * Every builder makes a piece facing +z (its front), with its back at -z, sitting on y = 0,
 * inside a box of width w (x), depth d (z) and height h (y), all in grid units (1 unit = 6 in).
 */

const M = {}
function mat(key, color, opts = {}) {
  if (!M[key]) {
    M[key] = new THREE.MeshStandardMaterial({ color, roughness: 0.7, ...opts })
    M[key].userData.shared = true
  }
  return M[key]
}
const WOOD = () => mat('wood', 0xa9784f, { roughness: 0.6 })
const DARKWOOD = () => mat('darkwood', 0x6b4a33, { roughness: 0.6 })
const FABRIC = () => mat('fabric', 0x8c9aa6, { roughness: 0.95 })
const WARMFABRIC = () => mat('warmfabric', 0xc7a27c, { roughness: 0.95 })
const LINEN = () => mat('linen', 0xf3eee4, { roughness: 0.95 })
const WHITE = () => mat('white', 0xf6f6f2, { roughness: 0.35 })
const STEEL = () => mat('steel', 0xb8bcc0, { roughness: 0.3, metalness: 0.6 })
const BLACK = () => mat('black', 0x2a2c2e, { roughness: 0.5 })
const GLASS = () => mat('glass', 0xbfe3f0, { roughness: 0.05, transparent: true, opacity: 0.3 })
const GREEN = () => mat('leaf', 0x4f8a4a, { roughness: 0.9 })
const POT = () => mat('pot', 0xb9704d, { roughness: 0.8 })
const GLOW = () => mat('glow', 0xfff1c4, { emissive: 0xffe08a, emissiveIntensity: 1.4 })
const RED = () => mat('red', 0xc0392b, { roughness: 0.5 })

function part(g, geo, material, x, y, z) {
  const m = new THREE.Mesh(geo, material)
  m.position.set(x, y, z)
  m.castShadow = true
  m.receiveShadow = true
  g.add(m)
  return m
}
const box = (g, w, h, d, m, x, y, z) => part(g, new THREE.BoxGeometry(w, h, d), m, x, y + h / 2, z)
const cyl = (g, r, h, m, x, y, z, seg = 16) => part(g, new THREE.CylinderGeometry(r, r, h, seg), m, x, y + h / 2, z)
function legs(g, w, d, h, r = 0.18, m = DARKWOOD()) {
  const ix = w / 2 - r * 1.5, iz = d / 2 - r * 1.5
  for (const [x, z] of [[-ix, -iz], [ix, -iz], [-ix, iz], [ix, iz]]) cyl(g, r, h, m, x, 0, z, 8)
}

const B = {
  bed(g, w, d, h) {
    box(g, w, h * 0.3, d, DARKWOOD(), 0, 0, 0)                          // frame
    box(g, w * 0.96, h * 0.25, d * 0.95, LINEN(), 0, h * 0.3, d * 0.02) // mattress
    box(g, w, h, 0.5, DARKWOOD(), 0, 0, -d / 2 + 0.25)                  // headboard
    const pw = w > 6 ? w * 0.42 : w * 0.8
    for (const x of w > 6 ? [-w * 0.24, w * 0.24] : [0]) box(g, pw, 0.6, 1.8, WHITE(), x, h * 0.55, -d / 2 + 1.6)
    box(g, w * 0.98, 0.25, d * 0.6, WARMFABRIC(), 0, h * 0.55, d * 0.18)  // blanket
  },
  sofa(g, w, d, h) {
    box(g, w, h * 0.35, d, FABRIC(), 0, 0, 0)
    box(g, w, h, d * 0.28, FABRIC(), 0, 0, -d / 2 + d * 0.14)
    for (const s of [-1, 1]) box(g, 0.9, h * 0.62, d, FABRIC(), s * (w / 2 - 0.45), 0, 0)
    const n = Math.max(1, Math.round((w - 1.8) / 3.2))
    const cw = (w - 1.8) / n
    for (let i = 0; i < n; i++) box(g, cw * 0.95, h * 0.18, d * 0.62, LINEN(), -w / 2 + 0.9 + cw * (i + 0.5), h * 0.35, d * 0.12)
  },
  armchair(g, w, d, h) { B.sofa(g, w, d, h) },
  chair(g, w, d, h, back = true) {
    const seat = Math.min(h * 0.55, 3.6)
    legs(g, w, d, seat, 0.12)
    box(g, w, 0.3, d, WOOD(), 0, seat, 0)
    if (back) box(g, w, h - seat, 0.25, WOOD(), 0, seat, -d / 2 + 0.12)
  },
  stool(g, w, d, h) {
    cyl(g, 0.15, h - 0.3, STEEL(), 0, 0, 0, 8)
    cyl(g, Math.min(w, d) / 2, 0.3, BLACK(), 0, h - 0.3, 0, 20)
  },
  table(g, w, d, h) {
    legs(g, w, d, h - 0.25)
    box(g, w, 0.25, d, WOOD(), 0, h - 0.25, 0)
  },
  desk(g, w, d, h) {
    B.table(g, w, d, h)
    box(g, w * 0.3, h * 0.75, d * 0.9, WOOD(), w * 0.33, 0, 0)          // drawer side
  },
  storage(g, w, d, h) {
    box(g, w, h, d, WOOD(), 0, 0, 0)
    const rows = Math.max(1, Math.round(h / 3))
    for (let i = 1; i < rows; i++) box(g, w * 0.98, 0.06, 0.05, DARKWOOD(), 0, (h / rows) * i, d / 2)
  },
  shelves(g, w, d, h) {
    const n = Math.max(2, Math.round(h / 2.4))
    for (const s of [-1, 1]) box(g, 0.2, h, d, WOOD(), s * (w / 2 - 0.1), 0, 0)
    for (let i = 0; i <= n; i++) box(g, w, 0.18, d, WOOD(), 0, (h - 0.18) * (i / n), 0)
    for (let i = 0; i < n; i++) box(g, w * 0.7, h / n * 0.6, d * 0.7, i % 2 ? WARMFABRIC() : FABRIC(), 0, (h / n) * i + 0.2, 0)
  },
  tv(g, w, d, h) {
    box(g, w, h * 0.45, d, DARKWOOD(), 0, 0, 0)
    box(g, w * 0.9, w * 0.5, 0.12, BLACK(), 0, h * 0.45 + 0.3, -d / 4)
  },
  fridge(g, w, d, h) {
    box(g, w, h, d, WHITE(), 0, 0, 0)
    box(g, w * 0.98, 0.04, 0.05, STEEL(), 0, h * 0.62, d / 2)
    box(g, 0.1, h * 0.25, 0.15, STEEL(), w * 0.38, h * 0.68, d / 2 + 0.07)
  },
  range(g, w, d, h) {
    box(g, w, h, d, STEEL(), 0, 0, 0)
    box(g, w, 0.05, d, BLACK(), 0, h, 0)
    for (const [x, z] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) cyl(g, w * 0.14, 0.06, STEEL(), x * w * 0.22, h, z * d * 0.22, 16)
  },
  appliance(g, w, d, h) {
    box(g, w, h, d, WHITE(), 0, 0, 0)
    part(g, new THREE.CircleGeometry(Math.min(w, h) * 0.3, 24), GLASS(), 0, h * 0.5, d / 2 + 0.01)
  },
  toilet(g, w, d, h) {
    box(g, w, h, d * 0.3, WHITE(), 0, 0, -d / 2 + d * 0.15)
    const b = cyl(g, w * 0.45, h * 0.55, WHITE(), 0, 0, d * 0.12, 20)
    b.scale.z = 1.35
  },
  vanity(g, w, d, h) {
    box(g, w, h * 0.92, d, WOOD(), 0, 0, 0)
    box(g, w, 0.15, d, WHITE(), 0, h * 0.92, 0)
    const sink = cyl(g, Math.min(w, d) * 0.28, 0.1, STEEL(), 0, h * 1.0, 0, 20)
    sink.scale.z = 0.8
    box(g, w * 0.8, w * 0.6, 0.06, GLASS(), 0, h * 1.25, -d / 2)        // mirror
  },
  tub(g, w, d, h) {
    box(g, w, h, d, WHITE(), 0, 0, 0)
    box(g, w * 0.82, 0.05, d * 0.86, mat('water', 0xcfe6ee, { roughness: 0.1 }), 0, h, 0)
  },
  shower(g, w, d, h) {
    box(g, w, 0.3, d, WHITE(), 0, 0, 0)
    box(g, w, h, d, GLASS(), 0, 0, 0)
  },
  floorLamp(g, w, d, h) {
    cyl(g, w * 0.35, 0.15, BLACK(), 0, 0, 0)
    cyl(g, 0.08, h * 0.8, BLACK(), 0, 0, 0, 8)
    part(g, new THREE.CylinderGeometry(w * 0.35, w * 0.5, h * 0.22, 20, 1, true), GLOW(), 0, h * 0.89, 0)
  },
  tableLamp(g, w, d, h) {
    cyl(g, w * 0.25, h * 0.5, POT(), 0, 0, 0)
    part(g, new THREE.CylinderGeometry(w * 0.35, w * 0.5, h * 0.45, 20, 1, true), GLOW(), 0, h * 0.75, 0)
  },
  plant(g, w, d, h) {
    cyl(g, w * 0.4, h * 0.35, POT(), 0, 0, 0)
    const leaf = part(g, new THREE.IcosahedronGeometry(w * 0.55, 1), GREEN(), 0, h * 0.62, 0)
    leaf.scale.y = 1.3
  },
  rug(g, w, d) { box(g, w, 0.08, d, mat('rug', 0xb5654a, { roughness: 1 }), 0, 0.01, 0) },
  curtains(g, w, d, h) { for (const s of [-1, 1]) box(g, w * 0.3, h, 0.3, WARMFABRIC(), s * w * 0.35, 0, 0) },
  art(g, w, d, h) {
    box(g, w, h, 0.12, DARKWOOD(), 0, 0, 0)
    box(g, w * 0.86, h * 0.86, 0.04, mat('canvas', 0x6f9fc0), 0, h * 0.07, 0.07)
  },
  mirror(g, w, d, h) { box(g, w, h, 0.1, mat('mirror', 0xdfe8ec, { roughness: 0.05, metalness: 0.8 }), 0, 0, 0) },
  grabBar(g) { const b = cyl(g, 0.07, 3.6, STEEL(), 0, 0, 0.2, 10); b.rotation.z = Math.PI / 2 },
  nightLight(g) { box(g, 0.45, 0.45, 0.15, GLOW(), 0, 0, 0) },
  smokeAlarm(g) { cyl(g, 0.5, 0.15, WHITE(), 0, 0, 0, 20) },
  fan(g, w) {
    cyl(g, 0.3, 0.4, WHITE(), 0, 0, 0)
    for (let i = 0; i < 4; i++) {
      const b = box(g, w * 0.48, 0.05, 0.6, WOOD(), 0, 0.1, 0)
      b.geometry.translate(w * 0.24, 0, 0)
      b.rotation.y = (Math.PI / 2) * i
    }
  },
  pendant(g, w) {
    cyl(g, 0.03, 2, BLACK(), 0, 0, 0, 6)
    part(g, new THREE.ConeGeometry(w * 0.45, w * 0.4, 20, 1, true), GLOW(), 0, -0.2, 0)
  },
  cylinderThing(g, w, d, h, m) { cyl(g, Math.min(w, d) * 0.45, h, m || WHITE(), 0, 0, 0) },
  booth(g, w, d, h) {
    box(g, w, h, 0.3, DARKWOOD(), 0, 0, -d / 2 + 0.15)
    for (const s of [-1, 1]) box(g, 0.3, h, d, DARKWOOD(), s * (w / 2 - 0.15), 0, 0)
    box(g, w, h, 0.1, GLASS(), 0, 0, d / 2)
    box(g, w, 0.3, d, DARKWOOD(), 0, h - 0.3, 0)
  },
  panel(g, w, d, h, m) { box(g, w, h, 0.3, m || mat('felt', 0x5f6f73, { roughness: 1 }), 0, 0, 0) },
  block(g, w, d, h, m) { box(g, w, h, d, m || WOOD(), 0, 0, 0) },
}

// which builder each catalog item uses, and how high wall items hang (inches)
const BY_ID = {
  'bed-queen': 'bed', 'bed-full': 'bed', 'bed-twin': 'bed', 'bed-king': 'bed',
  'sofa-3': 'sofa', 'sofa-2': 'sofa', 'lounge-sofa': 'sofa', 'outdoor-sofa': 'sofa',
  armchair: 'armchair', 'accent-chair': 'armchair', 'lounge-chair': 'armchair', 'waiting-chair': 'chair',
  'dining-chair': 'chair', 'desk-chair': 'chair', 'task-chair': 'chair', 'meet-chair': 'chair', 'cafe-chair': 'chair',
  'outdoor-chairs': 'chair', 'bar-stool': 'stool', 'pantry-stool': 'stool',
  'coffee-table': 'table', 'dining-4': 'table', 'dining-6': 'table', 'side-table': 'table', 'side-table-home': 'table',
  'cafe-table': 'table', 'outdoor-table': 'table', 'meet-4': 'table', 'meet-8': 'table', 'bench-desk-4': 'table',
  'kitchen-island': 'block', 'desk-home': 'desk', 'desk-office': 'desk', 'desk-standing': 'desk', 'reception-desk': 'block',
  dresser: 'storage', wardrobe: 'storage', nightstand: 'storage', sideboard: 'storage', cabinet: 'storage',
  pedestal: 'storage', locker: 'storage', 'bench-entry': 'storage', 'shoe-rack': 'shelves',
  bookshelf: 'shelves', shelves: 'shelves', 'tv-stand': 'tv',
  fridge: 'fridge', 'fridge-office': 'fridge', range: 'range', dishwasher: 'appliance', 'dishwasher-office': 'appliance',
  washer: 'appliance', dryer: 'appliance', microwave: 'appliance', 'microwave-office': 'appliance',
  toilet: 'toilet', 'toilet-office': 'toilet', vanity: 'vanity', 'sink-office': 'vanity', tub: 'tub', shower: 'shower',
  'floor-lamp': 'floorLamp', 'floor-lamp-office': 'floorLamp', 'table-lamp': 'tableLamp', 'desk-lamp': 'tableLamp',
  plant: 'plant', 'plant-office': 'plant', planter: 'plant', rug: 'rug', 'rug-office': 'rug',
  curtains: 'curtains', blackout: 'curtains', 'wall-art': 'art', 'wall-art-office': 'art', mirror: 'mirror',
  'grab-bar': 'grabBar', 'night-light': 'nightLight', 'smoke-alarm': 'smokeAlarm', 'ceiling-fan': 'fan',
  pendant: 'pendant', 'pendant-office': 'pendant', 'smart-bulbs': 'pendant', 'string-lights': 'pendant',
  'air-purifier': 'cylinderThing', 'air-purifier-office': 'cylinderThing', 'water-cooler': 'cylinderThing',
  extinguisher: 'cylinderThing', 'space-heater': 'block', 'window-ac': 'block', 'fan-office': 'floorLamp',
  'phone-booth': 'booth', 'acoustic-panel': 'panel', 'moss-wall': 'panel', divider: 'panel', whiteboard: 'panel',
  'screen-65': 'tv', monitor: 'panel', 'server-rack': 'block', printer: 'appliance', 'coffee-machine': 'appliance',
  'first-aid': 'panel', 'coat-rack': 'floorLamp',
}
// mounting height (inches above the floor) for things on walls and ceilings
const HANG_IN = { 'grab-bar': 34, 'night-light': 14, 'smoke-alarm': 94, 'ceiling-fan': 88, pendant: 80,
  'pendant-office': 84, 'smart-bulbs': 86, 'string-lights': 84, 'wall-art': 56, 'wall-art-office': 56, mirror: 30,
  curtains: 6, blackout: 6, 'acoustic-panel': 48, 'moss-wall': 48, 'first-aid': 48, monitor: 30, whiteboard: 20 }
const MATERIAL_BY_ID = { extinguisher: RED, 'server-rack': BLACK, 'space-heater': WHITE, 'window-ac': WHITE,
  'first-aid': WHITE, 'moss-wall': GREEN, whiteboard: WHITE, 'kitchen-island': WOOD, 'reception-desk': WOOD }

/**
 * Build one item. it: the item on the grid (x, y = center; w, d = footprint in cells).
 * cat: its catalog entry (size_in). facing: radians the front should face (toward the open room).
 */
export function buildItem(it, cat, cellIn, facing = 0) {
  const g = new THREE.Group()
  const kind = BY_ID[it.item] || 'block'
  const s = cat?.size_in || { w: it.w * cellIn, d: it.d * cellIn, h: 30 }
  // true size in grid units; the footprint on the map may be turned 90 degrees
  let w = s.w / cellIn, d = s.d / cellIn
  const h = Math.max(0.3, (s.h || 4) / cellIn)
  const turned = Math.abs(Math.sin(facing)) > 0.5
  if (kind === 'rug') { w = it.w; d = it.d }
  const inner = new THREE.Group()
  const thin = ['grabBar', 'nightLight', 'smokeAlarm', 'fan', 'pendant'].includes(kind)
  B[kind](inner, thin ? Math.max(w, 2) : w, d, h, MATERIAL_BY_ID[it.item]?.())
  inner.rotation.y = facing
  g.add(inner)
  const hang = HANG_IN[it.item]
  g.position.set(it.x, hang ? hang / cellIn : 0, it.y)
  g.userData = { kind, turned }
  return g
}

/** Which way an item should face: away from the wall it stands against (its back side). */
export function facingFor(it, grid) {
  const rows = grid.length, cols = grid[0].length
  const c0 = Math.round(it.x - it.w / 2), r0 = Math.round(it.y - it.d / 2)
  const c1 = c0 + Math.max(1, Math.round(it.w)), r1 = r0 + Math.max(1, Math.round(it.d))
  const solid = (r, c) => r < 0 || c < 0 || r >= rows || c >= cols || grid[r][c] < 0
  const count = (cells) => cells.filter(([r, c]) => solid(r, c)).length / Math.max(1, cells.length)
  const span = (a, b) => Array.from({ length: Math.max(1, b - a) }, (_, i) => a + i)
  const sides = [
    [count(span(c0, c1).map((c) => [r0 - 1, c])), 0],               // wall to the north → face south (+z)
    [count(span(c0, c1).map((c) => [r1, c])), Math.PI],             // wall south → face north
    [count(span(r0, r1).map((r) => [r, c0 - 1])), Math.PI / 2],     // wall west → face east
    [count(span(r0, r1).map((r) => [r, c1])), -Math.PI / 2],        // wall east → face west
  ]
  sides.sort((a, b) => b[0] - a[0])
  return sides[0][1]
}
