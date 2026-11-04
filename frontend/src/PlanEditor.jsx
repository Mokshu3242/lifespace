import { useEffect, useMemo, useRef, useState } from 'react'
import PlanCanvas from './PlanCanvas'
import { api } from './api'
import { CODES, KIND_LABEL, areaSqft, isMeta, modelLabel, roomColor } from './mapStyle'
import RedesignPanel from './RedesignPanel'
import PeoplePanel from './PeoplePanel'
import PlanDoctor from './PlanDoctor'
import View3D from './View3D'

const SOURCE_LABEL = {
  printed: 'Name read from the plan',
  'models agree': 'All models agreed',
  majority: 'Most models agreed',
  'most models': 'Most models agreed',
  'best size match': 'Closest size in the catalog',
  referee: 'Models disagreed; a referee picked',
  'one model': 'Only one model answered',
  none: 'No model could name it',
  you: 'Named by you',
}

const TOOLS = [
  { id: 'select', label: 'Select', hint: 'Click a room to select it.' },
  { id: 'room', label: 'Paint room', hint: 'Drag to add cells to the selected room.' },
  { id: 'wall', label: 'Wall', hint: 'Drag to draw walls.' },
  { id: 'erase', label: 'Blocked', hint: 'Drag to mark cells nobody can walk on (counters, tubs).' },
  { id: 'entrance', label: 'Entrance', hint: 'Click where the front door is.' },
]

const STEP_TABS = [
  { id: 'rooms', label: 'Plan', icon: '📐', help: 'Check rooms, sizes and doors', done: () => true },
  { id: 'items', label: 'Items', icon: '🛋️', help: 'Check the furniture found', done: () => false },
  { id: 'redesign', label: 'Redesign', icon: '✨', help: 'Fix it on a budget', done: ({ design }) => !!design },
  { id: 'people', label: 'People', icon: '👪', help: 'Watch them live a day', done: ({ sim }) => !!sim },
]

export default function PlanEditor({ space, onReset }) {
  const [grid, setGrid] = useState(space.grid)
  const [rooms, setRooms] = useState(space.rooms)
  const [entrance, setEntrance] = useState(space.entrance)
  const [selectedId, setSelectedId] = useState(space.rooms[0]?.id ?? null)
  const [items, setItems] = useState(space.items || [])
  const [doors, setDoors] = useState(space.doors || [])
  const [selectedItem, setSelectedItem] = useState(null)
  const [tab, setTab] = useState('rooms')
  const [catalog, setCatalog] = useState([])
  const [design, setDesign] = useState(null)
  const [showAfter, setShowAfter] = useState(true)
  const [sim, setSim] = useState(null)
  const [liveItems, setLiveItems] = useState(null)   // items while the improve loop plays on the map
  const [ghost, setGhost] = useState(null)           // an item being carried in or tried somewhere
  const [view, setView] = useState('2d')
  const [playing, setPlaying] = useState(false)
  const [focus, setFocus] = useState(null)
  const [step, setStep] = useState(0)          // cells walked so far in the playback
  const [tool, setTool] = useState('select')
  const [showPlan, setShowPlan] = useState(true)
  const [planImage, setPlanImage] = useState(null)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)
  const history = useRef([])

  useEffect(() => {
    const img = new Image()
    img.onload = () => setPlanImage(img)
    img.src = api.imageUrl(space.id)
  }, [space.id])

  useEffect(() => {
    api.catalog(space.pack || 'home').then((c) => setCatalog(c.items)).catch(() => {})
  }, [space.pack])

  // load the latest redesign right away, so People compares against it even if Redesign was never opened
  useEffect(() => {
    api.designs(space.id).then((v) => { if (v.length) setDesign((d) => d ?? v[v.length - 1]) }).catch(() => {})
  }, [space.id])

  // the people's day as one long path each, for playback
  const walks = useMemo(() => {
    if (!sim) return []
    const side = showAfter ? 'after' : 'before'
    return sim.personas.filter((p) => !focus || p.id === focus).map((p) => {
      const pts = [], marks = []
      for (const lg of sim[side][p.id].legs) {
        marks.push({ at: pts.length, label: `${lg.t} ${p.name} · ${lg.note}${lg.blocked ? ' (can\u2019t get there)' : ''}` })
        for (const pt of lg.path) pts.push(pt)
      }
      return { id: p.id, name: p.name, color: p.color, width: p.width_in, mobility: p.mobility, age: p.age, pts, marks }
    })
  }, [sim, showAfter, focus])

  useEffect(() => { setStep(0) }, [sim, showAfter, focus])

  useEffect(() => {
    if (!playing) return
    let raf, last = performance.now()
    const longest = Math.max(1, ...walks.map((w) => w.pts.length))
    const tick = (now) => {
      const dt = (now - last) / 1000
      last = now
      setStep((s) => {
        const next = s + dt * 45                 // cells per second of playback
        if (next >= longest) { setPlaying(false); return longest }
        return next
      })
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, walks])

  const people = walks.map((w) => {
    const i = Math.min(w.pts.length - 1, Math.floor(step))
    return { color: w.color, trail: w.pts.slice(Math.max(0, i - 400), i + 1), at: w.pts[Math.max(0, i)] }
  }).filter((p) => p.at)
  // squeeze spots of the day shown (or of the person picked), for the 2D map
  const squeezes = useMemo(() => {
    if (!sim || tab !== 'people') return []
    const side = showAfter ? 'after' : 'before'
    const out = []
    for (const p of sim.personas) {
      if (focus && p.id !== focus) continue
      for (const lg of sim[side][p.id]?.legs || []) for (const pt of lg.squeeze || []) out.push(pt)
    }
    return out
  }, [sim, tab, showAfter, focus])
  const clockWalk = walks[0]
  const clock = clockWalk && step > 0
    ? [...clockWalk.marks].reverse().find((m) => m.at <= step)?.label : null

  const selected = rooms.find((r) => r.id === selectedId)
  const totals = useMemo(() => {
    const out = {}
    for (const r of rooms) out[r.id] = areaSqft(grid, r.id, space.cell_in)
    return out
  }, [grid, rooms, space.cell_in])

  // warnings from the first read: drop "no name yet" once every room has a real name
  const unnamed = rooms.some((r) => /^Space \d+$/.test(r.name))
  const warnings = (space.warnings || []).filter((w) => !/no name yet/.test(w) || unnamed)
  const keptChanges = design ? (design.changes || []).filter((c) => !c.dropped).length : 0

  function paint(r, c, isFirst) {
    if (tool === 'select') {
      if (!isFirst) return
      const hit = items.find((it) => Math.abs(c + 0.5 - it.x) <= it.w / 2 + 0.5 && Math.abs(r + 0.5 - it.y) <= it.d / 2 + 0.5)
      if (hit) {
        setSelectedItem(hit.id)
        setTab('items')
        return
      }
      setSelectedItem(null)
      const v = grid[r][c]
      if (v >= 0) { setSelectedId(v); setTab('rooms') }
      return
    }
    if (tool === 'entrance') {
      setEntrance([c, r])
      setDirty(true)
      return
    }
    const value = tool === 'wall' ? CODES.WALL : tool === 'erase' ? CODES.FIXTURE : selectedId
    if (value == null || grid[r][c] === value) return
    if (isFirst) history.current.push(grid)
    setGrid((g) => {
      const next = g.map((row) => row.slice())
      next[r][c] = value
      return next
    })
    setDirty(true)
  }

  // a whole-map snapshot (AI fixes change rooms and doors too), so Undo brings all of it back
  function snapshot() { history.current.push({ grid, rooms, entrance, doors, items }) }

  function undo() {
    const prev = history.current.pop()
    if (!prev) return
    if (Array.isArray(prev)) setGrid(prev)
    else { setGrid(prev.grid); setRooms(prev.rooms); setEntrance(prev.entrance); setDoors(prev.doors); setItems(prev.items) }
    setDirty(true)
  }

  function rename(name) {
    setRooms((rs) => rs.map((r) => (r.id === selectedId
      ? { ...r, name, source: 'you', unsure: false, note: '' } : r)))
    setDirty(true)
  }

  function addRoom() {
    const id = rooms.reduce((m, r) => Math.max(m, r.id), -1) + 1
    setRooms((rs) => [...rs, { id, name: `Room ${id + 1}`, kind: 'room', dims_text: '' }])
    setSelectedId(id)
    setTool('room')
    setDirty(true)
  }

  const item = items.find((it) => it.id === selectedItem)
  const itemTotal = items.reduce((sum, it) => sum + (it.price_usd || 0), 0)

  function swapItem(catalogId) {
    const c = catalog.find((x) => x.id === catalogId)
    if (!c) return
    setItems((its) => its.map((it) => (it.id === selectedItem
      ? { ...it, item: c.id, name: c.name, chairs: 0, price_usd: c.price_usd, source: 'you', unsure: false, note: '' }
      : it)))
    setDirty(true)
  }

  function removeItem() {
    setItems((its) => its.filter((it) => it.id !== selectedItem))
    setSelectedItem(null)
    setDirty(true)
  }

  async function save() {
    setSaving(true)
    setMessage(null)
    try {
      const withAreas = rooms.map((r) => ({ ...r, area_sqft: totals[r.id] }))
      await api.saveSpace(space.id, { grid, rooms: withAreas, entrance, items, doors })
      setDirty(false)
      setMessage('Saved.')
    } catch (e) {
      setMessage(e.message)
    }
    setSaving(false)
  }

  const activeTool = TOOLS.find((t) => t.id === tool)

  return (
    <div className="editor three">
      <aside className="rail">
        <div className="rail-group">
          <span className="rail-title">View</span>
          <div className="tabs view-switch" role="tablist" aria-label="View">
            <button role="tab" aria-selected={view === '2d'} className={view === '2d' ? 'on' : ''} onClick={() => setView('2d')}>2D</button>
            <button role="tab" aria-selected={view === '3d'} className={view === '3d' ? 'on' : ''} onClick={() => setView('3d')}>3D</button>
          </div>
          {((tab === 'redesign' && design) || (tab === 'people' && sim)) && (
            <div className="tabs before-after">
              <button className={!showAfter ? 'on' : ''} onClick={() => setShowAfter(false)}>Before</button>
              <button className={showAfter ? 'on' : ''} onClick={() => setShowAfter(true)}>After</button>
            </div>
          )}
          <label className="toggle">
            <input type="checkbox" checked={showPlan} onChange={(e) => setShowPlan(e.target.checked)} />
            Show plan
          </label>
        </div>
        {view === '2d' && (
          <div className="rail-group">
            <span className="rail-title">Edit the map</span>
            {TOOLS.map((t) => (
              <button key={t.id} className={tool === t.id ? 'tool on' : 'tool'} onClick={() => setTool(t.id)} title={t.hint}>
                {t.label}
              </button>
            ))}
            <button className="tool" onClick={undo} disabled={!history.current.length}>↶ Undo</button>
          </div>
        )}
        <div className="rail-group">
          <span className="rail-title">This plan</span>
        <div className="chips rail-chips">
          <span className="chip-stat"><b>{rooms.length}</b> {rooms.length === 1 ? 'room' : 'rooms'}</span>
          <span className="chip-stat"><b>{Object.values(totals).reduce((a, b) => a + (b || 0), 0).toLocaleString()}</b> sq ft</span>
          <span className="chip-stat"><b>{doors.length}</b> {doors.length === 1 ? 'doorway' : 'doorways'}</span>
          {doors.some((d) => d.width_in < 30) && <span className="chip-stat warn-chip"><b>{doors.filter((d) => d.width_in < 30).length}</b> tight for a wheelchair</span>}
          <span className="chip-stat"><b>{items.length}</b> {items.length === 1 ? 'item' : 'items'} found</span>
          {design && <span className="chip-stat good-chip">Design {design.id}: <b>{keptChanges}</b> {keptChanges === 1 ? 'change' : 'changes'}</span>}
          {sim?.scores && <span className="chip-stat">Safety <b>{sim.scores.after.safety.score}</b> · Access <b>{sim.scores.after.access.score}</b></span>}
        </div>
          <p className="meta">
          {space.width_ft} × {space.height_ft} ft · 1 cell = {space.cell_in} in · scale {space.px_per_ft} px/ft
          ({space.scale_source})
          </p>
          <p className={isMeta(space.provider) ? 'powered meta' : 'powered'}>Plan read by {modelLabel(space.provider)}</p>
          {space.reused && <p className="meta reused">♻ Opened your saved read · no tokens used. Tick Fresh read on upload to read it again.</p>}
        </div>
      </aside>

      <div className="editor-main">
        <p className="hint">{view === '3d' ? 'The same map in 3D. Switch to 2D to edit rooms and walls.' : activeTool.hint}</p>
        <div className="canvas-wrap">
          {view === '3d' ? (
            <View3D space={{ ...space, doors }} grid={grid} rooms={rooms} catalog={catalog} planImage={planImage} showPlan={showPlan}
              people={tab === 'people' ? people : []} ghost={ghost} walks={walks}
              items={liveItems ? liveItems
                : (tab === 'redesign' || tab === 'people') && design
                  ? (showAfter ? design.items : items)
                  : items} />
          ) : (
          <PlanCanvas space={space} grid={grid} rooms={rooms} entrance={entrance}
            selectedId={selectedId} showPlan={showPlan} planImage={planImage} onPaint={paint}
            people={tab === 'people' ? people : []}
            ghost={ghost}
            items={liveItems ? liveItems
              : (tab === 'redesign' || tab === 'people') && design
                ? (showAfter ? design.items : items)
                : items}
            selectedItem={selectedItem} doors={doors} squeezes={squeezes} />
          )}
        </div>
        {view === '2d' && (
          <div className="legend" aria-label="Map key">
            <span><i className="k door-ok" />Doorway</span>
            <span><i className="k door-narrow" />Under 30 in (tight for a wheelchair)</span>
            <span><i className="k item" />Item found</span>
            <span><i className="k item-new" />New in the redesign</span>
            <span><i className="k item-gone" />Taken out</span>
            {tab === 'people' && sim && <span><i className="k squeeze" />Tight squeeze</span>}
            <span><i className="k front" />Front door</span>
          </div>
        )}
      </div>

      <aside className="sidebar">
        <div className="tabs" role="tablist">
          {STEP_TABS.map((t) => (
            <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'on' : ''}
              onClick={() => setTab(t.id)} title={t.help}>
              <span className="tab-ico" aria-hidden>{t.icon}</span>{t.label}
              {t.done({ design, sim }) && <span className="tab-done" aria-label="done">✓</span>}
            </button>
          ))}
        </div>
        {tab === 'people' ? (
          <PeoplePanel space={space} design={design} sim={sim} onSim={(s) => { setSim(s); setPlaying(Boolean(s)) }}
            showAfter={showAfter} playing={playing} onPlay={setPlaying} focus={focus} onFocus={setFocus} clock={clock} />
        ) : tab === 'redesign' ? (
          <RedesignPanel space={space} dirty={dirty} design={design} onDesign={setDesign}
            onShowAfter={setShowAfter} rooms={rooms} onHover={setSelectedItem} onLive={setLiveItems} onGhost={setGhost} />
        ) : tab === 'items' ? (
          <>
            {item ? (
              <div className="room-edit">
                <label>Item
                  <select value={item.item} onChange={(e) => swapItem(e.target.value)}>
                    {!catalog.some((c) => c.id === item.item) && <option value={item.item}>{item.name}</option>}
                    {catalog.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </label>
                <p className="meta">
                  {item.name} · ${item.price_usd} · {Math.round(item.w * space.cell_in / 12 * 10) / 10} × {Math.round(item.d * space.cell_in / 12 * 10) / 10} ft
                  {item.room != null && rooms.find((r) => r.id === item.room) ? ` · in ${rooms.find((r) => r.id === item.room).name}` : ''}
                </p>
                {item.source && (
                  <p className={item.unsure ? 'source unsure' : 'source'}>
                    {SOURCE_LABEL[item.source] || item.source}{item.unsure ? ' · please check' : ''}
                  </p>
                )}
                {item.note && <p className="note">{item.note}</p>}
                <button className="ghost small" onClick={removeItem}>Not furniture, remove</button>
              </div>
            ) : (
              <p className="hint">Click a dashed box on the map to check or change an item.</p>
            )}
            <ul className="room-list">
              {items.map((it) => (
                <li key={it.id} className={it.id === selectedItem ? 'on' : ''} onClick={() => setSelectedItem(it.id)}>
                  <span className="room-name">{it.name}</span>
                  {it.unsure && <span className="check" title="The models disagreed. Please check this item.">check</span>}
                  <span className="room-area">${it.price_usd}</span>
                </li>
              ))}
            </ul>
            {items.length > 0 && <p className="meta">Furniture already there: about ${itemTotal.toLocaleString()} at typical prices</p>}
          </>
        ) : (
        <>
        <div className="side-head">
          <h2>Rooms</h2>
          <button className="tool" onClick={addRoom}>+ Add</button>
        </div>
        {selected && (
          <div className="room-edit">
            <label>Name
              <input value={selected.name} onChange={(e) => rename(e.target.value)} />
            </label>
            <p className="meta">
              {KIND_LABEL[selected.kind] || selected.kind} · {totals[selected.id]} sq ft
              {selected.dims_text ? ` · printed ${selected.dims_text}` : ''}
            </p>
            {selected.source && (
              <p className={selected.unsure ? 'source unsure' : 'source'}>
                {SOURCE_LABEL[selected.source] || selected.source}
                {selected.unsure ? ' · please check' : ''}
              </p>
            )}
            {selected.note && <p className="note">{selected.note}</p>}
          </div>
        )}
        <ul className="room-list">
          {rooms.map((r) => (
            <li key={r.id} className={r.id === selectedId ? 'on' : ''} onClick={() => setSelectedId(r.id)}>
              <span className="swatch" style={{ background: roomColor(r.id) }} />
              <span className="room-name">{r.name}</span>
              {r.unsure && <span className="check" title="The models disagreed. Please check this name.">check</span>}
              <span className="room-area">{totals[r.id]} sq ft</span>
            </li>
          ))}
        </ul>
        </>
        )}
        {tab === 'rooms' && (
          <PlanDoctor space={space} doors={doors} onPreview={(pv) => {
            snapshot()
            setGrid(pv.grid); setRooms(pv.rooms); if (pv.entrance) setEntrance(pv.entrance)
            if (pv.doors) setDoors(pv.doors); if (pv.items) setItems(pv.items)
            setSelectedId(pv.rooms[0]?.id ?? null); setDirty(true)
            setMessage('AI fixes are on the map. Check them, then Save map (or Undo).')
          }} />
        )}
        {tab === 'rooms' && doors.length > 0 && (
          <details className="doors-found" open={doors.length <= 6}>
            <summary><strong>Doorways measured on the plan: {doors.length}</strong></summary>
            <ul>
              {[...doors].sort((a, b) => a.width_in - b.width_in).map((d, i) => (
                <li key={i} className={d.width_in < 30 ? 'narrow' : ''}>
                  {[...new Set(d.rooms.map((id) => rooms.find((r) => r.id === id)?.name).filter(Boolean))].join(' ↔ ') || 'Door'}{d.outside && ' (front door)'}{d.has_door === false && ' (open, no door)'}
                  {' · '}{d.width_in} in{d.width_in < 30 && ' · tight for a wheelchair'}{d.widened && ' · widened (what-if)'}
                </li>
              ))}
            </ul>
          </details>
        )}
        {(() => {
          const i = STEP_TABS.findIndex((t) => t.id === tab)
          const next = STEP_TABS[i + 1]
          return next && <button className="next-step" onClick={() => setTab(next.id)}>Next: {next.icon} {next.label} →<small>{next.help}</small></button>
        })()}
        {tab === 'rooms' && warnings.length > 0 && (
          <div className="warn">
            {warnings.map((w) => <p key={w}>{w}</p>)}
          </div>
        )}
        <div className="side-actions">
          <button onClick={save} disabled={!dirty || saving}>{saving ? 'Saving…' : 'Save map'}</button>
          <button className="ghost" onClick={onReset}>New plan</button>
        </div>
        {message && <p className="meta">{message}</p>}
      </aside>
    </div>
  )
}
