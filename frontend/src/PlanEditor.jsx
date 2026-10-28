import { useEffect, useMemo, useRef, useState } from 'react'
import PlanCanvas from './PlanCanvas'
import { api } from './api'
import { CODES, KIND_LABEL, areaSqft, roomColor } from './mapStyle'

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

  const selected = rooms.find((r) => r.id === selectedId)
  const totals = useMemo(() => {
    const out = {}
    for (const r of rooms) out[r.id] = areaSqft(grid, r.id, space.cell_in)
    return out
  }, [grid, rooms, space.cell_in])

  function paint(r, c, isFirst) {
    if (tool === 'select') {
      const v = grid[r][c]
      if (v >= 0) setSelectedId(v)
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
    setRooms((rs) => rs.map((r) => (r.id === selectedId ? { ...r, name } : r)))
    setDirty(true)
  }

  function addRoom() {
    const id = rooms.reduce((m, r) => Math.max(m, r.id), -1) + 1
    setRooms((rs) => [...rs, { id, name: `Room ${id + 1}`, kind: 'room', dims_text: '' }])
    setSelectedId(id)
    setTool('room')
    setDirty(true)
  }

  async function save() {
    setSaving(true)
    setMessage(null)
    try {
      const withAreas = rooms.map((r) => ({ ...r, area_sqft: totals[r.id] }))
      await api.saveSpace(space.id, { grid, rooms: withAreas, entrance })
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
            selectedId={selectedId} showPlan={showPlan} planImage={planImage} onPaint={paint} />
        </div>
        <p className="meta">
          {space.width_ft} × {space.height_ft} ft · 1 cell = {space.cell_in} in · scale {space.px_per_ft} px/ft
          ({space.scale_source}) · read by {space.provider}
        </p>
      </div>

      <aside className="sidebar">
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
          </div>
        )}
        <ul className="room-list">
          {rooms.map((r) => (
            <li key={r.id} className={r.id === selectedId ? 'on' : ''} onClick={() => setSelectedId(r.id)}>
              <span className="swatch" style={{ background: roomColor(r.id) }} />
              <span className="room-name">{r.name}</span>
              <span className="room-area">{totals[r.id]} sq ft</span>
            </li>
          ))}
        </ul>
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
