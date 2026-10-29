import { useEffect, useState } from 'react'
import PlanEditor from './PlanEditor'
import { api } from './api'
import './App.css'

const PACKS = [
  { id: 'home', label: 'Home' },
  { id: 'office', label: 'Office' },
  { id: 'street', label: 'Street', soon: true },
]

export default function App() {
  const [health, setHealth] = useState(null)
  const [backendDown, setBackendDown] = useState(false)
  const [space, setSpace] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const [fresh, setFresh] = useState(false)
  const [pack, setPack] = useState('home')
  const [describe, setDescribe] = useState('')

  useEffect(() => {
    api.health().then(setHealth).catch(() => setBackendDown(true))
    const id = new URLSearchParams(location.search).get('space')
    if (id) api.getSpace(id).then(setSpace).catch(() => {})
  }, [])

  async function upload(file) {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const s = await api.uploadPlan(file, { fresh, pack, describe })
      setSpace(s)
      history.replaceState(null, '', `?space=${s.id}`)
    } catch (e) {
      setError(e.message)
    }
    setBusy(false)
  }

  function reset() {
    setSpace(null)
    history.replaceState(null, '', location.pathname)
  }

  return (
    <main className={space ? 'shell wide' : 'shell'}>
      <header className="top">
        <div>
          <h1>LifeSpace</h1>
          <p className="tag">Design any space. Watch AI people live in it.</p>
        </div>
        {health && <span className="pill">{health.mode} mode</span>}
      </header>

      {backendDown && (
        <p className="bad">Backend not reachable. Start it with: uvicorn app.main:app --reload --port 8000</p>
      )}

      {!space && (
        <section
          className={dragOver ? 'drop on' : 'drop'}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); upload(e.dataTransfer.files[0]) }}
        >
          {busy ? (
            <>
              <div className="spinner" />
              <p>Reading your plan… the vision model looks at each space up close, so this takes 1 to 2 minutes locally.</p>
            </>
          ) : (
            <>
              <h2>Upload a floor plan</h2>
              <div className="packs" role="radiogroup" aria-label="Space type">
                {PACKS.map((p) => (
                  <button key={p.id} type="button" disabled={p.soon}
                    className={pack === p.id ? 'on' : ''} aria-pressed={pack === p.id}
                    onClick={() => setPack(p.id)}>
                    {p.label}{p.soon && <small> soon</small>}
                  </button>
                ))}
              </div>
              <input className="describe" maxLength={40} value={describe}
                onChange={(e) => setDescribe(e.target.value)}
                placeholder={pack === 'office' ? 'Describe it (optional): tech startup office' : 'Describe it (optional): 2-bed apartment'} />
              <p>Drop a PNG or JPG here, or choose a file. Plans with printed room sizes work best.</p>
              <label className="file-btn">
                Choose file
                <input type="file" accept="image/png,image/jpeg" onChange={(e) => upload(e.target.files[0])} hidden />
              </label>
              <label className="fresh">
                <input type="checkbox" checked={fresh} onChange={(e) => setFresh(e.target.checked)} />
                Fresh read (ignore saved AI answers)
              </label>
            </>
          )}
          {error && <p className="bad">{error}</p>}
        </section>
      )}

      {space && <PlanEditor key={space.id} space={space} onReset={reset} />}
    </main>
  )
}
