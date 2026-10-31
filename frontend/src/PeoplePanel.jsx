import { useEffect, useState } from 'react'
import { api } from './api'
import { isMeta, modelLabel } from './mapStyle'
import ScoreCard from './ScoreCard'

/** AI people live a day Before and After. Numbers come from code; voices from the model. */
export default function PeoplePanel({ space, design, sim, onSim, showAfter, playing, onPlay, focus, onFocus, clock }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [family, setFamily] = useState(null)
  const [text, setText] = useState('')
  const [making, setMaking] = useState(false)

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
      <button onClick={run} disabled={busy}>{busy ? 'Living the day…' : sim ? 'Run again' : 'Run a day'}</button>
      {error && <p className="bad">{error}</p>}

      {sim && (
        <>
          <ScoreCard scores={sim.scores} showAfter={showAfter} />
          <div className="play-row">
            <button className="tool" onClick={() => onPlay(!playing)}>{playing ? 'Pause' : 'Play the day'}</button>
            {clock && <span className="clock">{clock}</span>}
          </div>
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
                  {voice && <p className="voice">“{voice}”</p>}
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
