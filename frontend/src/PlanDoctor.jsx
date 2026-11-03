import { useState } from 'react'
import { api } from './api'
import { isMeta, modelLabel } from './mapStyle'

const ICON = { learned: '🧠', sliver: '🧩', unnamed: '🏷️', duplicate: '👯', entrance: '🚪', unreachable: '⛔', narrow_door: '↔️' }
const LABEL = { rename: 'Rename', merge: 'Merge', widen_door: 'Widen door', set_entrance: 'Front door', split: 'Split', add_item: 'Add' }

/** AI plan check: code finds problems, Muse Spark proposes fixes or follows what you ask, code applies
 *  them to the map in the editor. Nothing is saved until you press Save map. */
export default function PlanDoctor({ space, doors = [], onPreview }) {
  const [busy, setBusy] = useState(false)
  const [out, setOut] = useState(null)
  const [ask, setAsk] = useState('')
  const [error, setError] = useState(null)
  const [skip, setSkip] = useState({})
  const [step, setStep] = useState(null)      // the fix being put on the map right now, one at a time

  async function run(instruction = '') {
    setBusy(true); setError(null)
    try {
      const r = await api.doctor(space.id, { instruction, use_ai: true })
      setOut(r); setSkip({})
    } catch (e) { setError(e.message) }
    setBusy(false)
  }

  async function applyFixes() {
    const chosen = out.fixes.map((f, i) => ({ f, i })).filter(({ f, i }) => f.ok && !skip[i])
    setBusy(true); setError(null)
    try {
      // one fix at a time, like doing it by hand: code applies the first k fixes, the map updates, next
      for (let k = 1; k <= chosen.length; k++) {
        setStep(chosen[k - 1].i)
        const r = await api.doctor(space.id, { fixes: chosen.slice(0, k).map((c) => c.f.fix) }, k < chosen.length)
        onPreview(r.preview)
        if (k < chosen.length) await new Promise((res) => setTimeout(res, 700))
      }
      setOut({ ...out, applied: chosen.length })
    } catch (e) { setError(e.message) }
    setStep(null)
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
    : f.action === 'set_entrance' ? `opens into ${names[f.room] ?? f.room}`
    : f.action === 'split' ? `${names[f.room] ?? f.room} in two: new room “${f.name}”`
    : f.action === 'add_item' ? `${String(f.item).replace(/-/g, ' ')} in ${names[f.room] ?? f.room}` : f.action

  return (
    <details className="future doctor" open={!!out}>
      <summary>🩺 AI plan check <small>find and fix what was misread</small></summary>
      <p className="meta">Code checks the map, Muse Spark looks at your plan and suggests fixes. You choose what to keep. Every fix you keep teaches LifeSpace for the next plan.</p>
      <div className="future-row">
        <input value={ask} onChange={(e) => setAsk(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && run(ask)}
          placeholder="Or ask: split Dining and Hallway, add the bed drawn in Bedroom 2" disabled={busy} aria-label="Ask for a change" />
      </div>
      <button className="tool" onClick={() => run(ask)} disabled={busy}>{busy ? 'Checking…' : ask.trim() ? 'Make this change' : 'Check my plan'}</button>
      {error && <p className="bad">{error}</p>}
      {out && (
        <div className="future-out">
          {out.summary && <p>{out.summary}</p>}
          {out.learned_from > 0 && <p className="meta learned">🧠 Learned from {out.learned_from} fix{out.learned_from > 1 ? 'es' : ''} people accepted on earlier plans</p>}
          {out.issues.length > 0 && (
            <ul className="flags">{out.issues.map((x, i) => <li key={i}>{ICON[x.kind] || '•'} {x.text}</li>)}</ul>
          )}
          {out.issues.length === 0 && <p className="good">No problems found on the map.</p>}
          {out.fixes.length > 0 && (
            <>
              <strong>Suggested fixes</strong>
              <ul className="fix-list">
                {out.fixes.map((f, i) => (
                  <li key={i} className={`${f.ok ? '' : 'rejected'} ${step === i ? 'doing' : ''}`}>
                    <label>
                      <input type="checkbox" disabled={!f.ok} checked={f.ok && !skip[i]} onChange={() => setSkip((s) => ({ ...s, [i]: !s[i] }))} />
                      {step === i && <span className="pen" aria-hidden>✏️</span>}<b>{LABEL[f.fix.action] || f.fix.action}</b> {describe(f.fix)}
                    </label>
                    <div className="meta">{f.ok ? (f.fix.why || '') : `Can't do this: ${f.note}`}</div>
                  </li>
                ))}
              </ul>
              <button onClick={applyFixes} disabled={busy || !out.fixes.some((f, i) => f.ok && !skip[i])}>{step !== null ? 'Fixing the plan…' : 'Put these fixes on the map'}</button>
              {out.applied != null && <p className="meta">{out.applied} fixes on the map. Check them, then Save map, or Undo.</p>}
            </>
          )}
          {out.provider && <p className={isMeta(out.provider) ? 'powered meta' : 'powered'}>Fixes suggested by {modelLabel(out.provider)} · checked and applied by code</p>}
        </div>
      )}
    </details>
  )
}
