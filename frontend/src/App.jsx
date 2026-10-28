import { useEffect, useState } from 'react'
import './App.css'

export default function App() {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)
  const [prompt, setPrompt] = useState('Describe a cozy, accessible living room in one sentence.')
  const [answer, setAnswer] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setError('Backend not reachable. Is uvicorn running on port 8000?'))
  }, [])

  async function ask() {
    setBusy(true)
    setAnswer(null)
    try {
      const r = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      })
      const data = await r.json()
      setAnswer(r.ok ? data : { text: data.detail, provider: 'error' })
    } catch {
      setAnswer({ text: 'Request failed.', provider: 'error' })
    }
    setBusy(false)
  }

  return (
    <main className="shell">
      <header>
        <h1>LifeSpace</h1>
        <p className="tag">Design any space. Watch AI people live in it.</p>
      </header>

      <section className="card">
        <h2>System status</h2>
        {error && <p className="bad">{error}</p>}
        {health && (
          <ul className="status">
            <li>Mode: <strong>{health.mode}</strong></li>
            <li>Chat chain: {health.chain.chat.join(' → ')}</li>
            <li>Image chain: {health.chain.image.join(' → ')}</li>
          </ul>
        )}
        {!health && !error && <p>Checking backend…</p>}
      </section>

      <section className="card">
        <h2>Router test</h2>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} />
        <button onClick={ask} disabled={busy || !health}>
          {busy ? 'Asking…' : 'Ask the model'}
        </button>
        {answer && (
          <div className="answer">
            <p>{answer.text}</p>
            <p className="meta">answered by: {answer.provider}</p>
          </div>
        )}
      </section>
    </main>
  )
}
