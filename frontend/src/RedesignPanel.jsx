import { useEffect, useState } from 'react'
import { api } from './api'
import { isMeta, modelLabel } from './mapStyle'

const ACTION = { add: 'Add', replace: 'Replace', remove: 'Remove' }

/** Ask for a redesign inside a budget, then show what changed and why. */
export default function RedesignPanel({ space, dirty, design, onDesign, onShowAfter, rooms, onHover }) {
  const [budget, setBudget] = useState(1000)
  const [goals, setGoals] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [versions, setVersions] = useState([])

  useEffect(() => {
    api.designs(space.id).then((v) => {
      setVersions(v)
      if (v.length && !design) onDesign(v[v.length - 1])
    }).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [space.id])

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const d = await api.redesign(space.id, Number(budget), goals)
      setVersions((v) => [...v, d])
      onDesign(d)
      onShowAfter(true)
    } catch (e) {
      setError(e.message)
    }
    setBusy(false)
  }

  const roomName = (id) => rooms.find((r) => r.id === id)?.name || 'no room'
  const kept = design ? design.changes.filter((c) => !c.dropped) : []
  const dropped = design ? design.changes.filter((c) => c.dropped) : []

  return (
    <div className="redesign">
      <details className="new-design" open={!design}>
      <summary>{design ? 'New redesign' : 'Redesign this space'}</summary>
      <div className="room-edit">
        <label>Budget (USD)
          <input type="number" min={50} max={100000} step={50} value={budget}
            onChange={(e) => setBudget(e.target.value)} />
        </label>
        <label>Goals (optional)
          <textarea rows={2} maxLength={300} value={goals} onChange={(e) => setGoals(e.target.value)}
            placeholder={space.pack === 'office' ? 'quieter focus spots, better meetings' : 'safer for my parents, more storage'} />
        </label>
        {dirty && <p className="note">Save the map first so the redesign uses your fixes.</p>}
        <button onClick={run} disabled={busy || dirty}>{busy ? 'Designing…' : 'Redesign'}</button>
        {error && <p className="bad">{error}</p>}
      </div>
      </details>

      {versions.length > 1 && (
        <div className="versions">
          {versions.map((v) => (
            <button key={v.id} className={design?.id === v.id ? 'tool on' : 'tool'} onClick={() => onDesign(v)}>
              Design {v.id}
            </button>
          ))}
        </div>
      )}

      {design && (
        <>
          {design.summary && <p className="summary">{design.summary}</p>}
          <p className={isMeta(design.provider) ? 'powered meta' : 'powered'}>Designed by {modelLabel(design.provider)} · checked by code</p>
          <div className="spend">
            <div className="bar"><span className={design.spent_usd > design.budget_usd ? 'over' : ''}
              style={{ width: `${Math.min(100, (design.spent_usd / design.budget_usd) * 100)}%` }} /></div>
            <p className="spent"><strong>${design.spent_usd.toLocaleString()}</strong> of ${design.budget_usd.toLocaleString()}
              <span className="meta"> · {kept.length} changes</span></p>
          </div>
          <ul className="changes">
            {kept.map((c, i) => (
              <li key={i} className={`change ${c.action}`}
                onMouseEnter={() => c.placed && onHover(c.placed.id)} onMouseLeave={() => onHover(null)}>
                <span className={`act ${c.action}`}>{ACTION[c.action]}</span>
                <div>
                  <strong>{c.name}</strong> <span className="meta">in {roomName(c.room)}{c.cost_usd ? ` · $${c.cost_usd}` : ''}</span>
                  {c.reason && <p className="note">{c.reason}</p>}
                </div>
              </li>
            ))}
          </ul>
          {dropped.length > 0 && (
            <details className="dropped">
              <summary>{dropped.length} ideas rejected by the fit, budget and safety checks</summary>
              <ul>
                {dropped.map((c, i) => <li key={i}><strong>{c.name || c.item}</strong>: {c.dropped}</li>)}
              </ul>
            </details>
          )}
          {design.warnings?.map((w) => <p key={w} className="warn">{w}</p>)}
        </>
      )}
    </div>
  )
}
