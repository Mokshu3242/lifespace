import { useState } from 'react'
import { api } from './api'

const STARTERS = ['How was your day?', 'What was hard today?', 'What helped the most?', 'Anything you still can’t do?']

/** Talk to the people: each one answers in their own voice, only from their measured day. */
export default function TalkPanel({ space, design, showAfter, people }) {
  const [who, setWho] = useState(people[0]?.id)
  const [chats, setChats] = useState({})
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const designId = showAfter && design ? design.id : null
  const person = people.find((p) => p.id === who) || people[0]
  if (!person) return null
  const log = chats[person.id] || []

  async function send(text) {
    const message = (text ?? msg).trim()
    if (!message || busy) return
    const before = [...log, { who: 'you', text: message }]
    setChats((c) => ({ ...c, [person.id]: before })); setMsg(''); setBusy(true); setError(null)
    try {
      const a = await api.talk(space.id, person.id, message, log, designId)
      setChats((c) => ({ ...c, [person.id]: [...before, { who: 'them', text: a.reply }] }))
    } catch (e) { setError(e.message) }
    setBusy(false)
  }

  return (
    <details className="future talk">
      <summary>🗣️ Talk to them <small>ask about their day</small></summary>
      <div className="talk-who">
        {people.map((p) => (
          <button key={p.id} className={p.id === person.id ? 'chip on' : 'chip'} onClick={() => setWho(p.id)}
            style={{ borderColor: p.color }}><span style={{ color: p.color }}>●</span> {p.name}</button>
        ))}
      </div>
      <p className="meta">{person.name} answers only from the day measured on your plan{designId ? ' (after the redesign)' : ''}.</p>
      <div className="chat">
        {log.map((m, i) => (
          <p key={i} className={m.who === 'you' ? 'bubble you' : 'bubble them'}
            style={m.who === 'them' ? { borderColor: person.color } : undefined}>
            {m.who === 'them' && <strong style={{ color: person.color }}>{person.name} </strong>}{m.text}
          </p>
        ))}
        {busy && <p className="bubble them typing">{person.name} is thinking…</p>}
      </div>
      {log.length === 0 && (
        <div className="ask-ideas">{STARTERS.map((t) => <button key={t} className="chip" onClick={() => send(t)}>{t}</button>)}</div>
      )}
      <div className="future-row">
        <input value={msg} onChange={(e) => setMsg(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder={`Ask ${person.name} something`} aria-label={`Message to ${person.name}`} disabled={busy} />
        <button className="tool" onClick={() => send()} disabled={busy || !msg.trim()}>Send</button>
      </div>
      {error && <p className="bad">{error}</p>}
    </details>
  )
}
