import { useEffect, useState } from 'react'

/** The redesign as a shopping list: what to buy, room by room, with typical prices. Tick items off,
 *  copy the list as text, or print it. Ticks are kept in this browser only. */
export default function ShoppingList({ space, design, roomName }) {
  const [open, setOpen] = useState(false)
  const key = `lifespace-shop-${space.id}-${design.id}`
  const [got, setGot] = useState({})
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    try { setGot(JSON.parse(localStorage.getItem(key) || '{}')) } catch { setGot({}) }
  }, [key])
  const tick = (i) => setGot((g) => {
    const n = { ...g, [i]: !g[i] }
    try { localStorage.setItem(key, JSON.stringify(n)) } catch { /* private window: ticks just aren't kept */ }
    return n
  })

  const kept = design.changes.map((c, i) => ({ ...c, i })).filter((c) => !c.dropped)
  const buy = kept.filter((c) => c.action !== 'remove')
  const out = kept.filter((c) => c.action === 'remove')
  const rooms = [...new Set(buy.map((c) => c.room))]
  const total = buy.reduce((t, c) => t + (c.cost_usd || 0), 0)
  const left = buy.filter((c) => !got[c.i]).reduce((t, c) => t + (c.cost_usd || 0), 0)

  function asText() {
    const lines = [`LifeSpace shopping list · Design ${design.id}${design.goals ? ` · ${design.goals}` : ''}`, '']
    for (const r of rooms) {
      lines.push(roomName(r).toUpperCase())
      for (const c of buy.filter((x) => x.room === r)) lines.push(`[${got[c.i] ? 'x' : ' '}] ${c.name}  $${c.cost_usd || 0}${c.reason ? `  (${c.reason})` : ''}`)
      lines.push('')
    }
    if (out.length) {
      lines.push('TAKE OUT')
      for (const c of out) lines.push(`- ${c.name} from the ${roomName(c.room).toLowerCase()}`)
      lines.push('')
    }
    lines.push(`Total about $${total.toLocaleString()} at typical US prices`)
    return lines.join('\n')
  }
  async function copy() {
    try { await navigator.clipboard.writeText(asText()); setCopied(true); setTimeout(() => setCopied(false), 1800) } catch { setCopied(false) }
  }

  if (!buy.length && !out.length) return null
  return (
    <div className="shop">
      <button className="tool shop-open" onClick={() => setOpen((o) => !o)}>
        🛒 Shopping list · {buy.length} item{buy.length === 1 ? '' : 's'} · ${total.toLocaleString()}
      </button>
      {open && (
        <div className="shop-list" id="shop-print">
          <div className="shop-head">
            <strong>Shopping list</strong>
            <span className="meta">Design {design.id}{design.goals ? ` · ${design.goals}` : ''}</span>
          </div>
          {rooms.map((r) => (
            <section key={r}>
              <h4>{roomName(r)}</h4>
              <ul>
                {buy.filter((c) => c.room === r).map((c) => (
                  <li key={c.i} className={got[c.i] ? 'got' : ''}>
                    <label>
                      <input type="checkbox" checked={!!got[c.i]} onChange={() => tick(c.i)} />
                      <span className="shop-name">{c.name}</span>
                      <span className="shop-price">${c.cost_usd || 0}</span>
                    </label>
                    {c.reason && <div className="meta">{c.reason}</div>}
                  </li>
                ))}
              </ul>
            </section>
          ))}
          {out.length > 0 && (
            <section>
              <h4>Take out</h4>
              <ul>{out.map((c) => <li key={c.i} className="meta">{c.name} from the {roomName(c.room).toLowerCase()}</li>)}</ul>
            </section>
          )}
          <div className="shop-total">
            <span>Total <strong>${total.toLocaleString()}</strong></span>
            {left !== total && <span className="meta">still to buy ${left.toLocaleString()}</span>}
          </div>
          <p className="meta">Typical US retail prices. Every item was checked by code to fit where it goes.</p>
          <div className="shop-actions">
            <button className="tool" onClick={copy}>{copied ? 'Copied ✓' : 'Copy as text'}</button>
            <button className="tool" onClick={() => window.print()}>Print</button>
          </div>
        </div>
      )}
    </div>
  )
}
