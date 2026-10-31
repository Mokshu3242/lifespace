import { useEffect, useMemo, useRef, useState } from 'react'
import PlanCanvas from './PlanCanvas'
import { api } from './api'
import { CODES, KIND_LABEL, areaSqft, isMeta, modelLabel, roomColor } from './mapStyle'
import RedesignPanel from './RedesignPanel'

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

export default function PlanEditor({ space, onReset }) {
  const [grid, setGrid] = useState(space.grid)
  const [rooms, setRooms] = useState(space.rooms)
  const [entrance, setEntrance] = useState(space.entrance)
  const [selectedId, setSelectedId] = useState(space.rooms[0]?.id ?? null)
  const [items, setItems] = useState(space.items || [])
  const [selectedItem, setSelectedItem] = useState(null)
  const [tab, setTab] = useState('rooms')
  const [catalog, setCatalog] = useState([])
  const [design, setDesign] = useState(null)
  const [showAfter, setShowAfter] = useState(true)
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

  const selected = rooms.find((r) => r.id === selectedId)
  const totals = useMemo(() => {
    const out = {}
    for (const r of rooms) out[r.id] = areaSqft(grid, r.id, space.cell_in)
    return out
  }, [grid, rooms, space.cell_in])

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

  function undo() {
    const prev = history.current.pop()
    if (prev) { setGrid(prev); setDirty(true) }
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
      await api.saveSpace(space.id, { grid, rooms: withAreas, entrance, items })
      setDirty(false)
      setMessage('Saved.')
    } catch (e) {
      setMessage(e.message)
    }
    setSaving(false)
  }

  const activeTool = TOOLS.find((t) => t.id === tool)

  return (
    <div className="editor">
      <div className="editor-main">
        <div className="toolbar">
          {TOOLS.map((t) => (
            <button key={t.id} className={tool === t.id ? 'tool on' : 'tool'} onClick={() => setTool(t.id)}>
              {t.label}
            </button>
          ))}
          <button className="tool" onClick={undo} disabled={!history.current.length}>Undo</button>
          <label className="toggle">
            <input type="checkbox" checked={showPlan} onChange={(e) => setShowPlan(e.target.checked)} />
            Show plan
          </label>
        </div>
        <p className="hint">{activeTool.hint}</p>
        <div className="canvas-wrap">
          <PlanCanvas space={space} grid={grid} rooms={rooms} entrance={entrance}
            selectedId={selectedId} showPlan={showPlan} planImage={planImage} onPaint={paint}
            items={tab === 'redesign' && design
              ? (showAfter ? design.items.filter((it) => it.status === 'kept' || it.status === 'new') : items)
              : items}
            selectedItem={selectedItem} />
        </div>
        <p className="meta">
          {space.width_ft} × {space.height_ft} ft · 1 cell = {space.cell_in} in · scale {space.px_per_ft} px/ft
          ({space.scale_source})
        </p>
        <p className={isMeta(space.provider) ? 'powered meta' : 'powered'}>Plan read by {modelLabel(space.provider)}</p>
      </div>

      <aside className="sidebar">
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === 'rooms'} className={tab === 'rooms' ? 'on' : ''}
            onClick={() => setTab('rooms')}>Rooms ({rooms.length})</button>
          <button role="tab" aria-selected={tab === 'items'} className={tab === 'items' ? 'on' : ''}
            onClick={() => setTab('items')}>Items ({items.length})</button>
          <button role="tab" aria-selected={tab === 'redesign'} className={tab === 'redesign' ? 'on' : ''}
            onClick={() => setTab('redesign')}>Redesign</button>
        </div>
        {tab === 'redesign' ? (
          <RedesignPanel space={space} dirty={dirty} design={design} onDesign={setDesign}
            showAfter={showAfter} onShowAfter={setShowAfter} rooms={rooms} />
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
        {space.warnings?.length > 0 && (
          <div className="warn">
            {space.warnings.map((w) => <p key={w}>{w}</p>)}
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