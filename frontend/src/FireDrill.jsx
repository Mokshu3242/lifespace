import { useState } from 'react'
import { api } from './api'

const fmt = (s) => (s == null ? '—' : s >= 60 ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` : `${s}s`)

/** Fire drill at night: each person from their bed to the nearest way out, Before and After. Code only. */
export default function FireDrill({ space, design }) {
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function run() {
    setBusy(true); setError(null)
    try { setOut(await api.fireDrill(space.id, design?.id)) } catch (e) { setError(e.message) }
    setBusy(false)
  }

  const cell = (d) => !d.out ? <span className="bad">can't get out</span>
    : <span className={d.in_time ? 'good' : 'bad'}>{fmt(d.seconds)}</span>
  return (
    <details className="future">
      <summary>🔥 Fire drill <small>who gets out in time</small></summary>
      <p className="meta">{space.pack === 'office' ? "It's 2 PM and the alarm goes off. How long does each person take to get from their desk" : "It's 2 AM and the alarm goes off. How long does each person take to get from bed"} to the nearest way out{design ? ', before and after the redesign' : ''}?</p>
      <button className="tool" onClick={run} disabled={busy}>{busy ? 'Timing…' : 'Run the fire drill'}</button>
      {error && <p className="bad">{error}</p>}
      {out && (
        <div className="future-out">
          <p className={out.stuck.length ? 'bad' : out.everyone_out_s <= out.goal_s ? 'good' : 'bad'}>
            {out.stuck.length ? `${out.stuck.join(' and ')} can't get out alone.`
              : `Everyone out in ${fmt(out.everyone_out_s)} (aim: under ${fmt(out.goal_s)}).`}
          </p>
          <table className="drill">
            <thead><tr><th></th>{design && <th>Before</th>}<th>{design ? 'After' : 'Time'}</th></tr></thead>
            <tbody>
              {out.people.map((p) => (
                <tr key={p.id}>
                  <td><strong style={{ color: p.color }}>● {p.name}</strong>
                    <div className="meta">{p.after.out
                      ? `${p.after.from || 'start'} → ${p.after.exit}, ${p.after.ft} ft${p.after.tight_ft ? `, ${p.after.tight_ft} ft tight` : ''}`
                      : p.after.why}{p.after.note && ` · ${p.after.note}`}</div></td>
                  {design && <td>{cell(p.before)}</td>}
                  <td>{cell(p.after)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="meta">{out.note}</p>
        </div>
      )}
    </details>
  )
}
