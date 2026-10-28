import { useEffect, useState } from 'react'
import PlanEditor from './PlanEditor'
import { api } from './api'
import './App.css'

export default function App() {
  const [health, setHealth] = useState(null)
  const [backendDown, setBackendDown] = useState(false)
  const [space, setSpace] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [dragOver, setDragOver] = useState(false)

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
      const s = await api.uploadPlan(file)
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
              <p>Reading your plan… the vision model takes 20 to 60 seconds locally.</p>
            </>
          ) : (
            <>
              <h2>Upload a floor plan</h2>
              <p>Drop a PNG or JPG here, or choose a file. Plans with printed room sizes work best.</p>
              <label className="file-btn">
                Choose file
                <input type="file" accept="image/png,image/jpeg" onChange={(e) => upload(e.target.files[0])} hidden />
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
