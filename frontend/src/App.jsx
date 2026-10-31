import { useEffect, useState } from 'react'
import PlanEditor from './PlanEditor'
import HowItWorks from './HowItWorks'
import { api } from './api'
import './App.css'

const PACKS = [
  { id: 'home', label: 'Home' },
  { id: 'office', label: 'Office' },
  { id: 'street', label: 'Street', soon: true },
]

const STEPS = [
  { n: 1, title: 'Read your plan', text: 'Upload a floor plan. LifeSpace finds the walls, doors, rooms, sizes and furniture.' },
  { n: 2, title: 'Tell it who lives there', text: '“My dad is 74 and uses a walker.” Each person gets a real body width and a daily routine.' },
  { n: 3, title: 'Redesign on a budget', text: 'Real, common items only. Every idea is checked: does it fit, can it get through the door, does it block anyone?' },
  { n: 4, title: 'Watch them live it', text: 'The family lives the same day before and after. Paths, squeezes, blocked trips and scores are measured, not guessed.' },
]

const MODELS = [
  { name: 'Muse Spark 1.3', does: 'reads the plan, names rooms and furniture, plans the redesign, writes each person’s voice' },
  { name: 'Muse Image', does: 'draws the redesigned room from the real items in the design' },
  { name: 'SAM 3.1', does: 'tested for finding furniture on plans (great on shaded plans)' },
  { name: 'Muse Spark Open', does: 'backup on Baseten, same pipeline' },
]

function useRoute() {
  const [route, setRoute] = useState(location.hash || '#/')
  useEffect(() => {
    const on = () => setRoute(location.hash || '#/')
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

export default function App() {
  const route = useRoute()
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
      history.replaceState(null, '', `?space=${s.id}#/`)
    } catch (e) {
      setError(e.message)
    }
    setBusy(false)
  }

  function reset() {
    setSpace(null)
    history.replaceState(null, '', `${location.pathname}#/`)
  }

  const page = route.startsWith('#/how') ? 'how' : 'app'

  return (
    <div className="site">
      <header className="nav">
        <a className="brand" href="#/">
          <span className="logo" aria-hidden>◫</span> LifeSpace
        </a>
        <nav>
          <a href="#/" className={page === 'app' ? 'on' : ''}>{space ? 'Your space' : 'Start'}</a>
          <a href="#/how" className={page === 'how' ? 'on' : ''}>How it works</a>
        </nav>
        {health && <span className={health.mode === 'prod' ? 'pill meta-pill' : 'pill'}>
          {health.mode === 'prod' ? 'Live on Meta models' : `${health.mode} mode`}
        </span>}
      </header>

      <main className={space && page === 'app' ? 'shell wide' : 'shell'}>
        {backendDown && (
          <p className="bad">Backend not reachable. Start it with: uvicorn app.main:app --reload --port 8000</p>
        )}

        {page === 'how' && <HowItWorks models={MODELS} />}

        {page === 'app' && !space && (
          <>
            <section className="hero">
              <h1>Will this place work for the people who live in it?</h1>
              <p className="lead">
                Upload a floor plan, tell LifeSpace who lives there, and watch them live a day in it. It finds what
                would get in their way, fixes it with real furniture inside your budget, and proves the fix.
              </p>
            </section>

            <section
              className={dragOver ? 'drop on' : 'drop'}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); upload(e.dataTransfer.files[0]) }}
            >
              {busy ? (
                <>
                  <div className="spinner" />
                  <p>Reading your plan: walls, doors, rooms, printed sizes and furniture. About a minute.</p>
                </>
              ) : (
                <>
                  <h2>Start with a floor plan</h2>
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
                  <p>Drop a PNG or JPG here, or choose a file. Plans with printed room sizes read best.</p>
                  <label className="file-btn">
                    Choose a floor plan
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

            <section className="steps">
              {STEPS.map((s) => (
                <div key={s.n} className="step">
                  <span className="step-n">{s.n}</span>
                  <h3>{s.title}</h3>
                  <p>{s.text}</p>
                </div>
              ))}
            </section>

            <section className="promise">
              <h2>AI suggests. Code checks.</h2>
              <p>
                The models read, plan and talk. Every number you see is measured on your plan by code: walking
                distance, door widths, who gets blocked, budget. Ideas that don&apos;t pass are shown with the reason.
              </p>
              <ul className="models">
                {MODELS.map((m) => <li key={m.name}><strong>Meta {m.name}</strong> {m.does}</li>)}
              </ul>
              <a href="#/how" className="link">See how it works →</a>
            </section>
          </>
        )}

        {page === 'app' && space && <PlanEditor key={space.id} space={space} onReset={reset} />}
      </main>

      <footer className="foot">
        <p>LifeSpace · built for the Meta Global AI Developer Hackathon · Scores are measured from the floor plan for
          comparison only, not medical, safety or accessibility advice. Prices are typical US retail.</p>
      </footer>
    </div>
  )
}
