import { useState } from 'react'
import { api } from './api'
import { isMeta, modelLabel } from './mapStyle'

const ICON = { sliver: '🧩', unnamed: '🏷️', duplicate: '👯', entrance: '🚪', unreachable: '⛔', narrow_door: '↔️' }
const LABEL = { rename: 'Rename', merge: 'Merge', widen_door: 'Widen door', set_entrance: 'Front door' }

/** AI plan check: code finds problems, Muse Spark proposes fixes or follows what you ask, code applies
 *  them to the map in the editor. Nothing is saved until you press Save map. */
export default function PlanDoctor({ space, doors = [], onPreview }) {
  const [busy, setBusy] = useState(false)
  const [out, setOut] = useState(null)
  const [ask, setAsk] = useState('')
  const [error, setError] = useState(null)
  const [skip, setSkip] = useState({})

  async function run(instruction = '') {
    setBusy(true); setError(null)
    try {
      const r = await api.doctor(space.id, { instruction, use_ai: true })
      setOut(r); setSkip({})
    } catch (e) { setError(e.message) }
    setBusy(false)
  }

  async function applyFixes() {
    const fixes = out.fixes.filter((f, i) => f.ok && !skip[i]).map((f) => f.fix)
    setBusy(true); setError(null)
    try {
      const r = await api.doctor(space.id, { fixes })
      onPreview(r.preview)
      setOut({ ...out, applied: fixes.length })
    } catch (e) { setError(e.message) }
    setBusy(false)
  }

  const names = Object.fromEntries((space.rooms || []).map((r) => [r.id, r.name]))
  const doorName = (i) => {
    const d = doors[i]
    if (!d) return `door ${i}`
    return `${(d.rooms || []).map((x) => names[x] || '?').join(' ↔ ')}${d.outside ? ' front' : ''} (${d.width_in} in)`
  }
  const describe = (f) => f.action === 'rename' ? `${names[f.room] ?? `room ${f.room}`} → “${f.name}”`
    : f.action === 'merge' ? `${names[f.room] ?? f.room} into ${names[f.into] ?? f.into}`
    : f.action === 'widen_door' ? `${doorName(f.door)} door to ${f.width_in} in (renovation what-if)`
    : f.action === 'set_entrance' ? `opens into ${names[f.room] ?? f.room}` : f.action

  return (
    <details className="future doctor" open={!!out}>
      <summary>🩺 AI plan check <small>find and fix what was misread</small></summary>
      <p className="meta">Code checks the map, Muse Spark looks at your plan and suggests fixes. You choose what to keep.</p>
      <div className="future-row">
        <input value={ask} onChange={(e) => setAsk(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && run(ask)}
          placeholder="Or ask: widen the bath door to 32 in, rename Space 3 to Kitchen" disabled={busy} aria-label="Ask for a change" />
      </div>
      <button className="tool" onClick={() => run(ask)} disabled={busy}>{busy ? 'Checking…' : ask.trim() ? 'Make this change' : 'Check my plan'}</button>
      {error && <p className="bad">{error}</p>}
      {out && (
        <div className="future-out">
          {out.summary && <p>{out.summary}</p>}
          {out.issues.length > 0 && (
            <ul className="flags">{out.issues.map((x, i) => <li key={i}>{ICON[x.kind] || '•'} {x.text}</li>)}</ul>
          )}
          {out.issues.length === 0 && <p className="good">No problems found on the map.</p>}
          {out.fixes.length > 0 && (
            <>
              <strong>Suggested fixes</strong>
              <ul className="fix-list">
                {out.fixes.map((f, i) => (
                  <li key={i} className={f.ok ? '' : 'rejected'}>
                    <label>
                      <input type="checkbox" disabled={!f.ok} checked={f.ok && !skip[i]} onChange={() => setSkip((s) => ({ ...s, [i]: !s[i] }))} />
                      <b>{LABEL[f.fix.action] || f.fix.action}</b> {describe(f.fix)}
                    </label>
                    <div className="meta">{f.ok ? (f.fix.why || '') : `Can't do this: ${f.note}`}</div>
                  </li>
                ))}
              </ul>
              <button onClick={applyFixes} disabled={busy || !out.fixes.some((f, i) => f.ok && !skip[i])}>Put these fixes on the map</button>
              {out.applied != null && <p className="meta">{out.applied} fixes on the map. Check them, then Save map, or Undo.</p>}
            </>
          )}
          {out.provider && <p className={isMeta(out.provider) ? 'powered meta' : 'powered'}>Fixes suggested by {modelLabel(out.provider)} · checked and applied by code</p>}
        </div>
      )}
    </details>
  )
}
