import { useEffect, useState } from 'react'
import { api } from './api'
import { isMeta, modelLabel } from './mapStyle'
import ScoreCard from './ScoreCard'
import FuturePanel from './FuturePanel'
import FireDrill from './FireDrill'
import AskPanel from './AskPanel'
import TalkPanel from './TalkPanel'

/** AI people live a day Before and After. Numbers come from code; voices from the model. */
export default function PeoplePanel({ space, design, sim, onSim, showAfter, playing, onPlay, focus, onFocus, clock }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [family, setFamily] = useState(null)
  const [text, setText] = useState('')
  const [making, setMaking] = useState(false)
  const [comics, setComics] = useState({})
  const [drawing, setDrawing] = useState(null)

  async function addVisitor(kind) {
    setError(null)
    try { setFamily(await api.addVisitor(space.id, kind)); onSim(null) } catch (e) { setError(e.message) }
  }

  async function drawComic(pid) {
    if (!design) return
    setDrawing(pid); setError(null)
    try { const c = await api.comic(space.id, pid, design.id); setComics((m) => ({ ...m, [pid]: c })) } catch (e) { setError(e.message) }
    setDrawing(null)
  }

  useEffect(() => {
    api.family(space.id).then((f) => { if (f) { setFamily(f); setText(f.text) } }).catch(() => {})
  }, [space.id])

  async function makePeople() {
    setMaking(true)
    setError(null)
    try {
      const f = await api.describeFamily(space.id, text)
      setFamily(f)
      onSim(null)
    } catch (e) {
      setError(e.message)
    }
    setMaking(false)
  }

  async function useSamples() {
    await api.resetFamily(space.id).catch(() => {})
    setFamily(null)
    setText('')
    onSim(null)
  }

  async function run() {
    setBusy(true)
    setError(null)
    try {
      onSim(await api.simulate(space.id, design?.id ?? null))
    } catch (e) {
      setError(e.message)
    }
    setBusy(false)
  }

  const side = showAfter ? 'after' : 'before'
  return (
    <div className="people">
      <p className="note">
        Each person lives the same day Before and After{design ? ` Design ${design.id}` : ''}. Paths, distances
        and squeezes are measured on your plan.
      </p>
      <div className="who">
        <label>Who lives here?
          <textarea rows={3} maxLength={600} value={text} onChange={(e) => setText(e.target.value)}
            placeholder={space.pack === 'office'
              ? 'Ravi uses a wheelchair, Lena started this week, Omar runs the team'
              : 'My dad is 74 and uses a walker. My daughter is 6. I work from home.'} />
        </label>
        <div className="who-actions">
          <button className="tool" onClick={makePeople} disabled={making || text.trim().length < 3}>
            {making ? 'Meeting them…' : family ? 'Update people' : 'Make these people'}
          </button>
          {family && <button className="ghost small" onClick={useSamples}>Use sample people</button>}
        </div>
        {family && (
          <>
            <ul className="who-list">
              {family.people.map((p) => (
                <li key={p.id}><span className="dot" style={{ background: p.color }} /> <strong>{p.name}</strong> <span className="meta">{p.about} · needs {p.width_in} in to pass</span></li>
              ))}
            </ul>
            {family.notes?.length > 0 && <p className="note">{family.notes.join(' · ')}</p>}
            <p className={isMeta(family.provider) ? 'powered meta' : 'powered'}>People made by {modelLabel(family.provider)} · widths from standard sizes</p>
          </>
        )}
      </div>
      {space.pack !== 'office' && (
        <div className="visitors">
          <span className="meta">Add to the household:</span>
          {[['dog', '🐕 Dog'], ['toddler', '👶 Toddler'], ['caregiver', '🧑‍⚕️ Caregiver'], ['delivery', '📦 Delivery']].map(([k, label]) => (
            <button key={k} className="chip" onClick={() => addVisitor(k)} disabled={busy}>{label}</button>
          ))}
        </div>
      )}
      <button onClick={run} disabled={busy}>{busy ? 'Living the day…' : sim ? 'Run again' : 'Run a day'}</button>
      {error && <p className="bad">{error}</p>}
      <h3 className="whatif">What if…</h3>
      <FuturePanel space={space} design={design} showAfter={showAfter} />
      <FireDrill space={space} design={design} />
      {sim && <TalkPanel space={space} design={design} showAfter={showAfter} people={sim.personas} />}
      <AskPanel space={space} design={design} showAfter={showAfter} />

      {sim && (
        <>
          <ScoreCard scores={sim.scores} showAfter={showAfter} />
          <div className="play-row">
            <button className="tool" onClick={() => onPlay(!playing)}>{playing ? 'Pause' : 'Play the day'}</button>
            {clock && <span className="clock">{clock}</span>}
          </div>
          {design && sim.time_saved?.length > 0 && (() => {
            const total = sim.time_saved.reduce((t, x) => t + Math.max(0, x.minutes), 0)
            const trips = sim.time_saved.reduce((t, x) => t + Math.max(0, x.trips_unlocked), 0)
            return total > 0 && <p className="saved-total">⏱ The redesign saves this household about <strong>{Math.round(total)} min a day</strong>{trips > 0 && <> and makes <strong>{trips}</strong> more trip{trips > 1 ? 's' : ''} possible</>}.</p>
          })()}
          <ul className="persons">
            {sim.personas.map((p) => {
              const b = sim.before[p.id], a = sim.after[p.id]
              const d = sim[side][p.id]
              const voice = sim.voices?.[p.id]?.[side]
              const on = focus === p.id
              return (
                <li key={p.id} className={on ? 'person on' : 'person'} onClick={() => onFocus(on ? null : p.id)}>
                  <div className="person-head">
                    <span className="dot" style={{ background: p.color }} />
                    <strong>{p.name}</strong> <span className="meta">{p.about}</span>
                  </div>
                  <table className="stats">
                    <thead><tr><th /><th>Before</th><th>After</th></tr></thead>
                    <tbody>
                      <Row label="Walked" b={b.walked_ft} a={a.walked_ft} unit=" ft" lowerIsBetter />
                      <Row label="Tight squeezes" b={b.tight_ft} a={a.tight_ft} unit=" ft" lowerIsBetter />
                      <Row label="Couldn't get there" b={b.blocked} a={a.blocked} lowerIsBetter />
                    </tbody>
                  </table>
                  {(() => {
                    const ts = sim.time_saved?.find((x) => x.id === p.id)
                    return ts && design && (ts.minutes !== 0 || ts.trips_unlocked !== 0) && (
                      <p className={ts.minutes > 0 ? 'saved good' : 'saved bad'}>
                        {ts.minutes > 0 ? `⏱ Saves about ${ts.minutes} min a day` : `⏱ About ${-ts.minutes} min more a day`}
                        {ts.trips_unlocked > 0 && ` · ${ts.trips_unlocked} trip${ts.trips_unlocked > 1 ? 's' : ''} now possible`}
                      </p>
                    )
                  })()}
                  {voice && <p className="voice">“{voice}”</p>}
                  {on && design && (
                    <div className="comic" onClick={(e) => e.stopPropagation()}>
                      {!comics[p.id] && <button className="tool" disabled={drawing === p.id} onClick={() => drawComic(p.id)}>
                        {drawing === p.id ? 'Drawing the comic…' : `🎨 Comic of ${p.name}'s day`}</button>}
                      {comics[p.id] && (<>
                        <img src={comics[p.id].url} alt={`Comic of ${p.name}'s day, before and after`} />
                        <p className={isMeta(comics[p.id].provider) ? 'powered meta' : 'powered'}>Drawn by {modelLabel(comics[p.id].provider)} from {p.name}'s measured day</p>
                      </>)}
                    </div>
                  )}
                  {on && (
                    <ol className="legs">
                      {d.legs.map((lg, i) => (
                        <li key={i} className={lg.blocked ? 'blocked' : ''}>
                          <span className="t">{lg.t}</span> {lg.note}
                          {lg.blocked ? <span className="why"> · {lg.why}</span>
                            : <span className="meta"> · {lg.room}, {lg.ft} ft</span>}
                        </li>
                      ))}
                    </ol>
                  )}
                </li>
              )
            })}
          </ul>
          {sim.voice_provider && (
            <p className={isMeta(sim.voice_provider) ? 'powered meta' : 'powered'}>
              Voices by {modelLabel(sim.voice_provider)} · numbers measured by code
            </p>
          )}
          <p className="meta small">Measured from the floor plan for comparison only. Not medical or accessibility advice.</p>
        </>
      )}
    </div>
  )
}

function Row({ label, b, a, unit = '', lowerIsBetter }) {
  const diff = a - b
  const better = lowerIsBetter ? diff < 0 : diff > 0
  const cls = Math.abs(diff) < 0.5 ? '' : better ? 'good' : 'worse'
  return (
    <tr>
      <td>{label}</td>
      <td>{Math.round(b)}{unit}</td>
      <td className={cls}>{Math.round(a)}{unit}</td>
    </tr>
  )
}
