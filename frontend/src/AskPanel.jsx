import { useState } from 'react'
import { api } from './api'

const IDEAS = {
  home: ['Can my dad with a walker live here safely?', 'Is there a good spot to work from home?', 'Can everyone get out fast in a fire?'],
  office: ['Can a wheelchair user reach every room?', 'Is there a quiet place for calls?', 'Can everyone get out fast in a fire?'],
}
const BADGE = { yes: 'Yes', no: 'No', partly: 'Partly', 'not measured': 'Not measured' }

/** Ask LifeSpace: a plain question, answered only from what was measured on the plan. */
export default function AskPanel({ space, design, showAfter }) {
  const [q, setQ] = useState('')
  const [out, setOut] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const designId = showAfter && design ? design.id : null

  async function go(text) {
    const question = (text ?? q).trim()
    if (!question) return
    setBusy(true); setError(null); setQ(question)
    try {
      const a = await api.ask(space.id, question, designId)
      setOut((o) => [a, ...o].slice(0, 5)); setQ('')
    } catch (e) { setError(e.message) }
    setBusy(false)
  }

  return (
    <details className="future ask">
      <summary>Ask LifeSpace</summary>
      <p className="meta">Ask anything about {designId ? 'this redesign' : 'this place'}. The answer uses only what was measured on the plan.</p>
      <div className="ask-ideas">
        {(IDEAS[space.pack] || IDEAS.home).map((t) => <button key={t} className="chip" disabled={busy} onClick={() => go(t)}>{t}</button>)}
      </div>
      <div className="future-row">
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && go()}
          placeholder="Can my mom reach the bathroom at night?" aria-label="Your question" disabled={busy} />
        <button className="tool" onClick={() => go()} disabled={busy || !q.trim()}>{busy ? 'Thinking…' : 'Ask'}</button>
      </div>
      {error && <p className="bad">{error}</p>}
      {out.map((a, i) => (
        <div key={i} className="ask-answer">
          <div className="meta"><strong>{a.question}</strong></div>
          <p className="ask-text"><span className={`verdict v-${a.verdict.replace(' ', '-')}`}>{BADGE[a.verdict]}</span> {a.answer}</p>
          {a.facts.length > 0 && (
            <details><summary className="meta">Based on {a.facts.length} measured fact{a.facts.length > 1 ? 's' : ''}</summary>
              <ul className="flags">{a.facts.map((f, j) => <li key={j}>{f}</li>)}</ul></details>
          )}
          {a.provider && <p className="meta">Answered by {a.provider === 'meta' ? 'Meta Muse Spark 1.3' : a.provider} · facts measured by code</p>}
        </div>
      ))}
    </details>
  )
}
