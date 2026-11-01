import { useEffect, useState } from 'react'
import { api } from './api'

/** In 5 years: the same people, older, in the same home. What stops working, measured the same way as today. */
export default function FuturePanel({ space, design, showAfter }) {
  const [years, setYears] = useState(5)
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const designId = showAfter && design ? design.id : null
  const [secs, setSecs] = useState(0)
  useEffect(() => {
    if (!busy) return
    setSecs(0)
    const t = setInterval(() => setSecs((x) => x + 1), 1000)
    return () => clearInterval(t)
  }, [busy])
  const step = secs < 6 ? 'Ageing everyone and walking their day' : secs < 14 ? 'Measuring what still fits' : 'Asking each person how it feels'

  async function run() {
    setBusy(true); setError(null)
    try { setOut(await api.future(space.id, years, designId)) } catch (e) { setError(e.message) }
    setBusy(false)
  }

  const d = (k) => out && out.scores.then[k].score - out.scores.now[k].score
  return (
    <details className="future" open={!!out}>
      <summary>⏳ In {years} years <small>they get older</small></summary>
      <p className="meta">The same people, {years} years older, in {designId ? 'this redesign' : 'this home as it is'}. Who needs more room, and what stops working?</p>
      <div className="future-row">
        <select value={years} onChange={(e) => setYears(Number(e.target.value))} aria-label="Years from now">
          {[3, 5, 10, 15].map((y) => <option key={y} value={y}>{y} years</option>)}
        </select>
        <button className="tool" onClick={run} disabled={busy}>{busy ? 'Living the day…' : `Live a day ${years} years from now`}</button>
      </div>
      {busy && <p className="meta future-wait">{step}… {secs}s <span className="meta">(about a minute on Meta models)</span></p>}
      {error && <p className="bad">{error}</p>}
      {out && (
        <div className="future-out">
          <div className="future-scores">
            {[['access', 'Access'], ['movement', 'Movement'], ['safety', 'Safety']].map(([k, label]) => (
              <div key={k}><span>{label}</span><strong>{out.scores.now[k].score} → {out.scores.then[k].score}</strong>
                {d(k) !== 0 && <em className={d(k) < 0 ? 'down' : 'up'}>{d(k) > 0 ? '+' : ''}{d(k)}</em>}</div>
            ))}
          </div>
          <p className="meta">Access is checked for the widest person: today a {out.body_now.name} ({out.body_now.width_in} in), in {out.years} years a {out.body.name} ({out.body.width_in} in).</p>
          {out.breaks.length > 0 ? (
            <>
              <strong className="bad">What stops working ({out.breaks.length})</strong>
              <ul className="flags">{out.breaks.map((b, i) => <li key={i}><strong>{b.person}</strong> · {b.t} {b.note}: {b.why}</li>)}</ul>
            </>
          ) : out.still?.length > 0
            ? <p className="meta"><strong>Nothing new breaks, but these were already blocked and stay blocked:</strong> {out.still.join(', ')}.{d('access') < 0 && ' Access drops because the wider chair has less room in the rooms it can reach.'}</p>
            : <p className="good">Nothing new stops working for these people.</p>}
          <ul className="persons">
            {out.people.map((p) => (
              <li key={p.id}>
                <strong style={{ color: p.color }}>● {p.name}</strong> <span className="meta">{p.about}</span>
                {p.change && <div className="meta">Assumed: {p.change}{p.width_in !== p.was_width_in && ` (needs ${p.width_in} in, was ${p.was_width_in})`}</div>}
                <div className="meta">Today {p.now.walked_ft} ft, {p.now.blocked} blocked → then {p.then.walked_ft} ft, {p.then.blocked} blocked</div>
                {out.voices[p.id] && <p className="voice">“{out.voices[p.id]}”</p>}
              </li>
            ))}
          </ul>
          <p className="meta">{out.note}{out.provider && ` · Voices by ${out.provider}`}</p>
        </div>
      )}
    </details>
  )
}
