import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { isMeta, modelLabel } from './mapStyle'

const ACTION = { add: 'Add', replace: 'Replace', remove: 'Remove' }

/** Ask for a redesign inside a budget, then show what changed and why. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

export default function RedesignPanel({ space, dirty, design, onDesign, onShowAfter, rooms, onHover, onLive, onGhost }) {
  const [budget, setBudget] = useState(1000)
  const [goals, setGoals] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [versions, setVersions] = useState([])
  const [pictureRoom, setPictureRoom] = useState(null)
  const [picture, setPicture] = useState(null)
  const [drawing, setDrawing] = useState(false)
  const [big, setBig] = useState(false)
  const [target, setTarget] = useState(80)
  const [timeline, setTimeline] = useState(null)
  const [improving, setImproving] = useState(false)

  const [log, setLog] = useState([])
  const logRef = useRef(null)
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [log])

  // One item's way in: carried along its path from the front door, the spots tried first
  // (red, with the real reason), then set down where it fits.
  async function playItem(item, delivery, tries, say) {
    if (delivery?.length > 1) {
      const step = Math.max(1, Math.round(delivery.length / 60))
      for (let i = 0; i < delivery.length; i += step) {
        const [c, r] = delivery[i]
        onGhost({ x: c + 0.5, y: r + 0.5, w: item.w, d: item.d, tone: 'carry', label: `Carrying ${item.name}`,
          trail: delivery.slice(0, i + 1) })
        await sleep(28)
      }
    }
    for (const t of tries || []) {
      say({ kind: 'try', text: `Tried ${t.where}: ${t.why}` })
      onGhost({ ...t, tone: 'bad', label: t.why, trail: delivery })
      await sleep(1100)
    }
    onGhost({ x: item.x, y: item.y, w: item.w, d: item.d, tone: 'ok', label: `${item.name} fits here`, trail: delivery })
    await sleep(700)
    onGhost(null)
  }

  // Replay any design's changes the same way (for designs made with one Redesign click)
  const [replaying, setReplaying] = useState(false)
  async function replay() {
    if (!design) return
    setReplaying(true)
    setLog([])
    onShowAfter(true)
    const say = (e) => setLog((l) => [...l, e])
    let live = design.items.filter((it) => it.status !== 'new').map((it) => ({ ...it, status: it.status === 'kept' ? 'kept' : it.status }))
    live = live.map((it) => ({ ...it, status: 'kept' }))
    onLive(live)
    for (const th of design.thoughts || []) { say({ kind: 'thought', text: `Thinking: ${th}` }); await sleep(1200) }
    for (const c of design.changes) {
      const where = roomName(c.room)
      if (c.dropped) {
        say({ kind: 'rejected', text: `Rejected: ${c.name}${where ? ' in ' + where : ''}. ${c.dropped}` })
        await sleep(800)
        continue
      }
      if (c.swapped_from) { say({ kind: 'swap', text: `Won't fit: ${c.swapped_from} → trying ${c.name}` }); await sleep(1200) }
      if (c.action === 'remove' && c.replaces != null) {
        say({ kind: 'change', text: `Removing ${c.name}${where ? ' in ' + where : ''}` })
        live = live.map((it) => (it.id === c.replaces ? { ...it, status: 'removed' } : it))
        onLive(live)
        await sleep(900)
        continue
      }
      if (!c.placed) continue
      say({ kind: 'change', text: `${c.action === 'replace' ? 'Replacing with' : 'Adding'} ${c.name}${where ? ' in ' + where : ''}${c.cost_usd ? `, $${c.cost_usd}` : ''}${c.carry ? ` · ${c.carry}` : ''}` })
      await playItem(c.placed, c.delivery, c.tries, say)
      if (c.replaces != null) live = live.map((it) => (it.id === c.replaces ? { ...it, status: 'replaced' } : it))
      live = [...live, { ...c.placed, status: 'new' }]
      onLive(live)
      onHover(c.placed.id)
      await sleep(500)
    }
    onHover(null)
    onLive(null)
    setReplaying(false)
  }

  // Run the improve loop as a job and play its steps one by one on the map and in the log.
  async function improveLoop() {
    setImproving(true)
    setError(null)
    setLog([])
    setTimeline(null)
    onShowAfter(true)
    let live = (space.items || []).map((it) => ({ ...it, status: 'kept' }))
    onLive(live)
    const queue = []
    let finished = false
    try {
      const { job } = await api.improve(space.id, { budget: Number(budget), goals, target_safety: Number(target), rounds: 3 })
      let since = 0
      let serverDone = false
      ;(async () => {
        try {
          while (!serverDone) {
            const res = await api.improveProgress(space.id, job, since)
            queue.push(...res.events)
            since = res.next
            serverDone = res.done
            if (!serverDone) await sleep(1000)
          }
        } catch (e) {
          queue.push({ kind: 'error', text: e.message })
          serverDone = true
        }
      })()
      // play events at a watchable pace, until the server is done and every step has been shown
      while (!finished) {
        const ev = queue.shift()
        if (!ev) {
          if (serverDone) break
          await sleep(300)
          continue
        }
        setLog((l) => [...l, ev])
        if (ev.kind === 'change' && ev.item) {
          await playItem(ev.item, ev.delivery, ev.tries, (e) => setLog((l) => [...l, e]))
          live = [...live, { ...ev.item, status: 'new' }]
          onLive(live)
          onHover(ev.item.id)
          await sleep(400)
        } else if (ev.kind === 'thought' || ev.kind === 'swap') {
          await sleep(1200)
        } else if (ev.kind === 'change' && ev.action === 'remove' && ev.replaces != null) {
          live = live.map((it) => (it.id === ev.replaces ? { ...it, status: 'removed' } : it))
          onLive(live)
          await sleep(900)
        } else if (ev.kind === 'rejected') {
          await sleep(700)
        } else if (ev.kind === 'scores') {
          const v = await api.designs(space.id)
          setVersions(v)
          const d = v.find((x) => x.id === ev.design_id)
          if (d) { onDesign(d); live = d.items; onLive(live) }
          await sleep(1200)
        } else if (ev.kind === 'done') {
          setTimeline({ rounds: ev.rounds, final_design_id: ev.final_design_id })
          finished = true
        } else if (ev.kind === 'error') {
          setError(ev.text)
          finished = true
        } else {
          await sleep(600)
        }
      }
    } catch (e) {
      setError(e.message)
    }
    finished = true
    onHover(null)
    onLive(null)
    setImproving(false)
  }

  useEffect(() => { setPicture(null) }, [design?.id, pictureRoom])

  async function draw() {
    const roomId = pictureRoom ?? changedRooms[0]
    if (roomId == null) return
    setDrawing(true)
    setError(null)
    try {
      setPicture(await api.renderRoom(space.id, design.id, roomId))
    } catch (e) {
      setError(e.message)
    }
    setDrawing(false)
  }

  useEffect(() => {
    api.designs(space.id).then((v) => {
      setVersions(v)
      if (v.length && !design) onDesign(v[v.length - 1])
    }).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [space.id])

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const d = await api.redesign(space.id, Number(budget), goals)
      setVersions((v) => [...v, d])
      onDesign(d)
      onShowAfter(true)
    } catch (e) {
      setError(e.message)
    }
    setBusy(false)
  }

  const roomName = (id) => rooms.find((r) => r.id === id)?.name || 'no room'
  const kept = design ? design.changes.filter((c) => !c.dropped) : []
  const changedRooms = [...new Set(kept.map((c) => c.room).filter((r) => r != null))]
  const dropped = design ? design.changes.filter((c) => c.dropped) : []

  return (
    <div className="redesign">
      <details className="new-design" open={!design}>
      <summary>{design ? 'New redesign' : 'Redesign this space'}</summary>
      <div className="room-edit">
        <label>Budget (USD)
          <input type="number" min={50} max={100000} step={50} value={budget}
            onChange={(e) => setBudget(e.target.value)} />
        </label>
        <label>Goals (optional)
          <textarea rows={2} maxLength={300} value={goals} onChange={(e) => setGoals(e.target.value)}
            placeholder={space.pack === 'office' ? 'quieter focus spots, better meetings' : 'safer for my parents, more storage'} />
        </label>
        {dirty && <p className="note">Save the map first so the redesign uses your fixes.</p>}
        <div className="design-actions">
          <button onClick={run} disabled={busy || dirty || improving}>{busy ? 'Designing…' : 'Redesign'}</button>
          <span className="or">or</span>
          <button className="tool" onClick={improveLoop} disabled={busy || dirty || improving}>
            {improving ? 'Improving… (up to 3 rounds)' : 'Keep improving until Safety'}
          </button>
          <input className="target" type="number" min={0} max={100} value={target}
            onChange={(e) => setTarget(e.target.value)} aria-label="Target safety score" />
        </div>
        {error && <p className="bad">{error}</p>}
      </div>
      </details>

      {log.length > 0 && (
        <ol className="live-log" aria-live="polite" ref={logRef}>
          {log.filter((e) => e.text && e.kind !== 'done').map((e, i) => (
            <li key={i} className={e.kind}>{e.text}</li>
          ))}
          {improving && <li className="thinking">Muse Spark is working…</li>}
        </ol>
      )}

      {timeline && (
        <ol className="timeline">
          {timeline.rounds.map((r) => (
            <li key={r.round} className={design?.id === r.design_id ? 'on' : ''}
              onClick={() => { const d = versions.find((v) => v.id === r.design_id); if (d) onDesign(d) }}>
              <strong>Round {r.round}</strong>
              <span className={r.met ? 'good' : ''}> Safety {r.scores.safety}{r.met ? ' ✓' : ''}</span>
              <span className="meta"> · Access {r.scores.access} · ${r.spent_usd.toLocaleString()} so far</span>
              {r.added.length > 0 && <p className="note">Added: {r.added.join(', ')}</p>}
            </li>
          ))}
          {!timeline.rounds.at(-1)?.met && (
            <li className="meta">Stopped after {timeline.rounds.length} rounds. What&apos;s left needs work furniture can&apos;t do (see the flags in People).</li>
          )}
        </ol>
      )}

      {versions.length > 1 && (
        <div className="versions">
          {versions.map((v) => (
            <button key={v.id} className={design?.id === v.id ? 'tool on' : 'tool'} onClick={() => onDesign(v)}>
              Design {v.id}
            </button>
          ))}
        </div>
      )}

      {design && (
        <>
          {design.summary && <p className="summary">{design.summary}</p>}
          <button className="tool watch" onClick={replay} disabled={replaying || improving}>
            {replaying ? 'Furnishing…' : '▶ Watch it being furnished'}
          </button>
          <p className={isMeta(design.provider) ? 'powered meta' : 'powered'}>Designed by {modelLabel(design.provider)} · checked by code</p>
          <div className="spend">
            <div className="bar"><span className={design.spent_usd > design.budget_usd ? 'over' : ''}
              style={{ width: `${Math.min(100, (design.spent_usd / design.budget_usd) * 100)}%` }} /></div>
            <p className="spent"><strong>${design.spent_usd.toLocaleString()}</strong> of ${design.budget_usd.toLocaleString()}
              <span className="meta"> · {kept.length} changes</span></p>
          </div>
          <ul className="changes">
            {kept.map((c, i) => (
              <li key={i} className={`change ${c.action}`}
                onMouseEnter={() => c.placed && onHover(c.placed.id)} onMouseLeave={() => onHover(null)}>
                <span className={`act ${c.action}`}>{ACTION[c.action]}</span>
                <div>
                  <strong>{c.name}</strong> <span className="meta">in {roomName(c.room)}{c.cost_usd ? ` · $${c.cost_usd}` : ''}</span>
                  {c.reason && <p className="note">{c.reason}</p>}
                </div>
              </li>
            ))}
          </ul>
          {dropped.length > 0 && (
            <details className="dropped">
              <summary>{dropped.length} {dropped.length === 1 ? "idea" : "ideas"} rejected by the fit, budget and safety checks</summary>
              <ul>
                {dropped.map((c, i) => <li key={i}><strong>{c.name || c.item}</strong>: {c.dropped}</li>)}
              </ul>
            </details>
          )}
          {design.warnings?.map((w) => <p key={w} className="warn">{w}</p>)}
          {changedRooms.length > 0 && (
            <div className="picture">
              <h3>See it</h3>
              <div className="picture-row">
                <select value={pictureRoom ?? changedRooms[0]} onChange={(e) => setPictureRoom(Number(e.target.value))}>
                  {changedRooms.map((id) => <option key={id} value={id}>{roomName(id)}</option>)}
                </select>
                <button onClick={draw} disabled={drawing}>{drawing ? 'Drawing…' : 'Picture this room'}</button>
              </div>
              {picture && (
                <>
                  <button className="picture-open" onClick={() => setBig(true)} title="See it full size">
                    <img src={`${picture.url}?v=${design.id}`} alt={`The redesigned ${roomName(pictureRoom ?? changedRooms[0])}`} />
                  </button>
                  {big && (
                    <div className="lightbox" role="dialog" aria-label="Room picture" onClick={() => setBig(false)}>
                      <img src={`${picture.url}?v=${design.id}`} alt={`The redesigned ${roomName(pictureRoom ?? changedRooms[0])}`} />
                      <p>{roomName(pictureRoom ?? changedRooms[0])} · drawn by {modelLabel(picture.provider)} from the real items in this design · click to close</p>
                    </div>
                  )}
                  <p className={isMeta(picture.provider) ? 'powered meta' : 'powered'}>
                    Drawn by {modelLabel(picture.provider)} from the real items in this design
                  </p>
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
