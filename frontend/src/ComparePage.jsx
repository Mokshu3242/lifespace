import { useEffect, useState } from 'react'
import { api } from './api'

const SCORES = [['access', 'Access'], ['movement', 'Movement'], ['safety', 'Safety'], ['energy', 'Energy']]

/** Apartment chooser: the same people live the same day in 2 or 3 plans. Code ranks; Muse Spark explains. */
export default function ComparePage() {
  const [plans, setPlans] = useState(null)
  const [picked, setPicked] = useState([])
  const [family, setFamily] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [open, setOpen] = useState(null)          // the layout whose options are showing
  const [upPack, setUpPack] = useState('home')
  const [uploading, setUploading] = useState(false)

  const load = () => api.listSpaces().then(setPlans).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  function toggle(ref) {
    setPicked((p) => (p.includes(ref) ? p.filter((x) => x !== ref) : p.length < 3 ? [...p, ref] : p))
  }

  async function upload(file) {
    if (!file) return
    setUploading(true); setError(null)
    try {
      const s = await api.uploadPlan(file, { pack: upPack })
      await load()
      setOpen(s.id)
      setPicked((p) => (p.length < 3 && !p.includes(s.id) ? [...p, s.id] : p))
    } catch (e) { setError(e.message) }
    setUploading(false)
  }

  async function run() {
    setBusy(true); setError(null); setResult(null)
    try { setResult(await api.compare(picked, family)) } catch (e) { setError(e.message) }
    setBusy(false)
  }

  const layoutOf = (ref) => (plans || []).find((g) => g.id === ref.split(':')[0] || g.designs.some((d) => d.ref === ref))
  const pack = picked.length ? layoutOf(picked[0])?.pack : null
  const nameOf = (ref) => {
    const g = layoutOf(ref)
    const d = g?.designs.find((x) => x.ref === ref)
    return `${g?.describe || (g?.pack === 'office' ? 'Office' : 'Home')} · ${d ? `Redesign ${d.label}` : 'as it is'}`
  }

  return (
    <article className="compare">
      <h1>Which home fits them?</h1>
      <p className="lead">Pick 2 or 3 options: different homes, or the same home as it is and after a redesign. The same
        people live the same day in each one. Code measures who can get where; <strong>Muse Spark</strong> explains the pick.</p>

      <div className="compare-upload">
        <div className="packs">
          {['home', 'office'].map((k) => (
            <button key={k} type="button" className={upPack === k ? 'on' : ''} onClick={() => setUpPack(k)}>
              {k === 'home' ? 'Home' : 'Office'}</button>
          ))}
        </div>
        <label className="file-btn">{uploading ? 'Reading the plan… about a minute' : 'Add a new plan'}
          <input type="file" accept="image/png,image/jpeg" hidden disabled={uploading}
            onChange={(e) => upload(e.target.files[0])} />
        </label>
      </div>

      {!plans && !error && <p className="meta">Loading your plans…</p>}
      {plans && plans.length > 0 && (
        <div className="plan-pick">
          {plans.map((g) => {
            const refs = [g.id, ...g.designs.map((d) => d.ref)]
            const chosen = refs.filter((r) => picked.includes(r))
            const off = pack && g.pack !== pack
            return (
              <div key={g.id} className={chosen.length ? 'plan-card on' : 'plan-card'} aria-disabled={off}>
                <button className="plan-face" disabled={off} onClick={() => setOpen(open === g.id ? null : g.id)}>
                  <img alt="" src={`/api/spaces/${g.id}/image`} />
                  <strong>{g.describe || (g.pack === 'office' ? 'Office' : 'Home')} · {g.size_ft[0]} × {g.size_ft[1]} ft</strong>
                  <span className="meta">{g.rooms.slice(0, 4).join(', ')}{g.rooms.length > 4 ? '…' : ''}</span>
                  <span className="meta">{g.designs.length ? `${g.designs.length} redesign${g.designs.length > 1 ? 's' : ''}` : 'no redesigns yet'}
                    {chosen.length > 0 && ` · ${chosen.length} picked`}</span>
                </button>
                {open === g.id && !off && (
                  <div className="plan-options">
                    {refs.map((r) => {
                      const d = g.designs.find((x) => x.ref === r)
                      const on = picked.includes(r)
                      return (
                        <button key={r} className={on ? 'tool on' : 'tool'} disabled={!on && picked.length >= 3}
                          onClick={() => toggle(r)} title={d?.summary || 'The plan with its furniture as it is now'}>
                          {on && `${picked.indexOf(r) + 1}. `}{d ? `Redesign ${d.label} · $${Math.round(d.spent_usd).toLocaleString()} · ${d.changes} changes` : 'As it is'}
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
      {picked.length > 0 && <p className="meta">Picked: {picked.map((r, i) => `${i + 1}. ${nameOf(r)}`).join('  ·  ')}</p>}

      {plans && plans.length > 0 && (
        <div className="compare-form">
          <label>Who will live there? (optional)
            <textarea rows={2} maxLength={600} value={family} onChange={(e) => setFamily(e.target.value)}
              placeholder={pack === 'office' ? 'Ravi uses a wheelchair; Lena is new; Omar runs the team'
                : 'My dad Ramesh is 74 and uses a walker. My daughter is 6. I work from home.'} />
          </label>
          <button onClick={run} disabled={busy || picked.length < 2}>
            {busy ? 'Living the day in each one…' : picked.length < 2 ? 'Pick 2 or 3 options' : `Compare ${picked.length} options`}
          </button>
          {error && <p className="bad">{error}</p>}
        </div>
      )}

      {result && (
        <section className="compare-result">
          <div className="verdict">
            <h2>Plan {result.pick} fits them best</h2>
            {result.why && <p>{result.why}</p>}
            <p className="meta">Ranked by code from the measured day · explained by {result.provider || 'code only'}</p>
          </div>
          <div className="compare-cols" style={{ gridTemplateColumns: `repeat(${result.plans.length}, minmax(0, 1fr))` }}>
            {result.plans.map((pl, i) => (
              <div key={pl.id} className={pl.rank === 1 ? 'compare-col best' : 'compare-col'}>
                <img alt="" src={`/api/spaces/${pl.id}/image`} />
                <h3>Plan {i + 1} {pl.rank === 1 && <span className="badge add">Best fit</span>}</h3>
                <p className="meta">{nameOf(picked[i] || pl.id)} · {pl.size_ft[0]} × {pl.size_ft[1]} ft · {pl.rooms} rooms</p>
                {pl.good && <p className="good">✓ {pl.good}</p>}
                {pl.bad && <p className="bad-soft">✗ {pl.bad}</p>}
                {pl.deal_breakers.length > 0 && (
                  <ul className="flags breakers">{pl.deal_breakers.map((d) => <li key={d}>{d}</li>)}</ul>
                )}
                {SCORES.map(([k, label]) => (
                  <div key={k} className="score-mini"><span>{label}</span><strong>{pl.scores[k].score}</strong>
                    <div className="bar"><span style={{ width: `${pl.scores[k].score}%` }} /></div></div>
                ))}
                <table className="who">
                  <thead><tr><th>Person</th><th>Walked</th><th>Blocked</th></tr></thead>
                  <tbody>{pl.people.map((p) => (
                    <tr key={p.id} className={p.must.length ? 'bad-row' : ''}><td>{p.name}</td><td>{p.walked_ft} ft</td><td>{p.blocked}</td></tr>
                  ))}</tbody>
                </table>
                <a className="link" href={`?space=${pl.id}#/`}>Open this plan →</a>
              </div>
            ))}
          </div>
          <p className="meta">Measured from the floor plans for comparison only. Not medical or accessibility advice.</p>
        </section>
      )}
    </article>
  )
}
