import { useState } from 'react'
import { api } from './api'

const KIND = {
  light: ['Street light', '#e0a800'], bench: ['Bench', '#2f9e6b'], bin: ['Bin', '#5a6b7a'],
  sidewalk: ['Sidewalk', '#2f7fd6'], pole: ['Pole', '#c0392b'], tree: ['Tree', '#3c8d3c'],
  crosswalk: ['Crosswalk', '#8e44ad'], curb_ramp: ['Curb ramp', '#8e44ad'], car: ['Parked car', '#7f8c8d'],
  steps: ['Steps', '#d35400'], bus_stop: ['Bus stop', '#16a085'], planter: ['Planter', '#3c8d3c'],
}
const SCORES = [['walk', 'Walk and wheel'], ['cross', 'Crossing'], ['rest', 'Rest'], ['light', 'Night light'],
  ['shade', 'Shade'], ['clean', 'Clean']]

/** A street photo: what Meta SAM 3.1 found, what Muse Spark read, a scorecard by code, a redesign,
 *  and Muse Image drawing the fixes onto the real photo. */
const plural = (w, n) => (n === 1 ? w : /(ch|sh|s|x)$/.test(w) ? `${w}es` : `${w}s`)

export default function StreetView({ street: initial, onReset }) {
  const [street, setStreet] = useState(initial)
  const [show, setShow] = useState(true)
  const [budget, setBudget] = useState(20000)
  const [goals, setGoals] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState(null)
  const [view, setView] = useState('before')
  const [stamp, setStamp] = useState(0)
  const design = street.designs?.[street.designs.length - 1] || null
  const [w, h] = street.size
  const sc = street.scene || {}
  const scores = design ? design.after : street.scores

  async function redesign() {
    setBusy('design'); setError(null)
    try {
      const d = await api.redesignStreet(street.id, Number(budget), goals)
      setStreet((s) => ({ ...s, designs: [...(s.designs || []), d] }))
      setView('before')
    } catch (e) { setError(e.message) }
    setBusy('')
  }

  async function draw() {
    setBusy('draw'); setError(null)
    try {
      await api.drawStreet(street.id, design.n)
      setStamp(Date.now())
      setStreet((s) => ({ ...s, designs: s.designs.map((d) => (d.n === design.n ? { ...d, drawn: true } : d)) }))
      setView('after')
    } catch (e) { setError(e.message) }
    setBusy('')
  }

  const counts = {}
  for (const t of street.things) counts[t.kind] = (counts[t.kind] || 0) + 1

  return (
    <div className="street">
      <div className="street-main">
        <div className="street-tools">
          {design?.drawn && (
            <div className="seg two">
              <button className={view === 'before' ? 'on' : ''} onClick={() => setView('before')}>Before</button>
              <button className={view === 'after' ? 'on' : ''} onClick={() => setView('after')}>After (Muse Image)</button>
            </div>
          )}
          {view === 'before' && street.things.length > 0 && (
            <label className="fresh"><input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} />
              Show what SAM 3.1 found</label>
          )}
        </div>
        <div className="street-photo">
          <img alt="The street" src={view === 'after' && design
            ? `/api/streets/${street.id}/designs/${design.n}/render?t=${stamp}` : `/api/streets/${street.id}/photo`} />
          {view === 'before' && show && (
            <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden>
              {street.things.map((t, i) => {
                const [label, color] = KIND[t.kind] || [t.word, '#333']
                const [x1, y1, x2, y2] = t.box
                return (
                  <g key={i}>
                    <rect x={x1} y={y1} width={x2 - x1} height={y2 - y1} fill="none" stroke={color} strokeWidth={Math.max(2, w / 400)} />
                    <text x={x1 + 2} y={Math.max(12, y1 - 4)} fill={color} fontSize={Math.max(11, w / 70)} fontWeight="700"
                      stroke="#fff" strokeWidth={3} paintOrder="stroke">{label}</text>
                  </g>
                )
              })}
            </svg>
          )}
        </div>
        <p className="meta">
          {street.things.length ? <>Found by <strong>Meta SAM 3.1</strong>: {Object.entries(counts).map(([k, n]) => `${n} ${plural((KIND[k]?.[0] || k).toLowerCase(), n)}`).join(', ')}. </> : 'SAM 3.1 runs on Meta models only (prod). '}
          {sc.summary && <>Read by <strong>Muse Spark</strong>: {sc.summary}</>}
        </p>
      </div>

      <aside className="panel street-side">
        <h2>Street check</h2>
        <p className="meta">Surface: {sc.surface}{sc.rail_tracks ? ' with rail tracks' : ''} · sidewalk {sc.sidewalk_width} · shade {sc.shade} · {sc.trees} trees</p>
        <div className="scorecard">
          <div className="score-row overall"><strong>Overall</strong>
            <span>{design ? <>{design.before.overall} → <strong>{design.after.overall}</strong></> : street.scores.overall}</span></div>
          {SCORES.map(([k, label]) => {
            const b = (design ? design.before : street.scores)[k]
            const a = scores[k]
            return (
              <div key={k} className="score-row">
                <div className="score-head"><strong>{label}</strong>
                  <span>{design && a.score !== b.score ? <>{b.score} → <strong>{a.score}</strong> <em className="up">+{a.score - b.score}</em></> : a.score}</span></div>
                <div className="bar"><span style={{ width: `${a.score}%` }} /></div>
                <p className="meta">{a.why}</p>
              </div>
            )
          })}
        </div>
        {scores.flags.length > 0 && (
          <details open><summary>{design ? 'Still a problem' : 'Problems found'} ({scores.flags.length})</summary>
            <ul className="flags">{scores.flags.map((f) => <li key={f}>{f}</li>)}</ul></details>
        )}

        <details className="new-design" open={!design}>
          <summary>{design ? 'New street redesign' : 'Fix this street'}</summary>
          <label>Budget (USD)
            <input type="number" min={500} step={500} value={budget} onChange={(e) => setBudget(e.target.value)} />
          </label>
          <label>Goals (optional)
            <textarea rows={2} maxLength={300} value={goals} onChange={(e) => setGoals(e.target.value)}
              placeholder="easier for wheelchairs and older people" />
          </label>
          <button onClick={redesign} disabled={!!busy}>{busy === 'design' ? 'Designing…' : 'Redesign the street'}</button>
        </details>

        {design && (
          <div className="street-design">
            <p>{design.summary}</p>
            <p className="spent"><strong>${design.spent_usd.toLocaleString()}</strong> of ${design.budget_usd.toLocaleString()} · {design.changes.length} fixes</p>
            <ul className="changes">
              {design.changes.map((c, i) => (
                <li key={i}><span className="badge add">Add</span> <strong>{c.name}</strong> · ${c.price_usd.toLocaleString()}
                  <br /><span className="meta">{c.where}{c.reason && ` · ${c.reason}`}</span></li>
              ))}
            </ul>
            {design.dropped?.length > 0 && <details><summary>{design.dropped.length} not used</summary>
              <ul>{design.dropped.map((d, i) => <li key={i}>{d.item}: {d.why}</li>)}</ul></details>}
            <button onClick={draw} disabled={!!busy}>{busy === 'draw' ? 'Drawing… (about 30 s)' : 'Draw it on the photo (Muse Image)'}</button>
            <p className="meta">Designed by {design.provider} · scores measured by code</p>
          </div>
        )}
        {error && <p className="bad">{error}</p>}
        <button className="tool" onClick={onReset}>New photo</button>
      </aside>
    </div>
  )
}
