async function handle(r) {
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || `Request failed (${r.status})`)
  return data
}

// Calls go straight to the backend when VITE_API_URL is set (the live site): Cloudflare's proxy cuts
// requests off at 100 seconds, and a plan read or a redesign on Meta can take longer than that.
// Pictures still load through the site's own /api path.
const API = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

// Judge pass: open the site once with ?key=CODE and that browser skips the daily AI limit.
const KEY = (() => {
  try {
    const m = (location.search + location.hash).match(/[?&]key=([^&#]+)/)
    if (m) localStorage.setItem('ls_key', decodeURIComponent(m[1]))
    return localStorage.getItem('ls_key') || ''
  } catch { return '' }
})()
const fetch = (url, opt = {}) =>
  window.fetch(url, KEY ? { ...opt, headers: { ...(opt.headers || {}), 'X-Demo-Key': KEY } } : opt)

// plans uploaded in this browser, so the Compare page can show them next to the samples
const mine = () => { try { return JSON.parse(localStorage.getItem('ls_mine') || '[]') } catch { return [] } }
const remember = (s) => {
  try { if (s && s.id) localStorage.setItem('ls_mine', JSON.stringify([...new Set([s.id, ...mine()])].slice(0, 20))) } catch {}
  return s
}

export const api = {
  health: () => fetch(API + '/api/health').then(handle),
  uploadPlan: (file, { fresh = false, pack = 'home', describe = '' } = {}) => {
    const body = new FormData()
    body.append('file', file)
    const q = new URLSearchParams({ pack, describe: describe.trim() })
    if (fresh) q.set('fresh', 'true')
    return fetch(`${API}/api/spaces?${q}`, { method: 'POST', body }).then(handle).then(remember)
  },
  getSpace: (id) => fetch(`${API}/api/spaces/${id}`).then(handle),
  listSpaces: () => fetch(`${API}/api/spaces?mine=${encodeURIComponent(mine().join(','))}`).then(handle),
  ask: (id, question, designId) =>
    fetch(`${API}/api/spaces/${id}/ask`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, design_id: designId ?? null }),
    }).then(handle),
  fireDrill: (id, designId) =>
    fetch(`${API}/api/spaces/${id}/firedrill`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ design_id: designId ?? null }),
    }).then(handle),
  future: (id, years, designId) =>
    fetch(`${API}/api/spaces/${id}/future`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ years, design_id: designId ?? null }),
    }).then(handle),
  compare: (ids, family) =>
    fetch(API + '/api/spaces/compare', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids, family }),
    }).then(handle),
  uploadStreet: (file) => {
    const body = new FormData()
    body.append('file', file)
    return fetch(API + '/api/streets', { method: 'POST', body }).then(handle)
  },
  getStreet: (id) => fetch(`${API}/api/streets/${id}`).then(handle),
  redesignStreet: (id, budget, goals) =>
    fetch(`${API}/api/streets/${id}/designs`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ budget, goals }),
    }).then(handle),
  drawStreet: (id, n) => fetch(`${API}/api/streets/${id}/designs/${n}/render`, { method: 'POST' }).then(handle),
  redesign: (id, budget, goals, style = 'small') =>
    fetch(`${API}/api/spaces/${id}/designs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ budget, goals, style }),
    }).then(handle),
  simulate: (id, designId) =>
    fetch(`${API}/api/spaces/${id}/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ design_id: designId }),
    }).then(handle),
  restyle: (id, designId, roomId, file) => {
    const body = new FormData()
    body.append('file', file)
    return fetch(`${API}/api/spaces/${id}/designs/${designId}/restyle?room_id=${roomId}`, { method: 'POST', body }).then(handle)
  },
  doctor: (id, body, step = false) =>
    fetch(`${API}/api/spaces/${id}/doctor${step ? '?apply=1' : ''}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).then(handle),
  addVisitor: (id, kind) =>
    fetch(`${API}/api/spaces/${id}/family/add`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind }),
    }).then(handle),
  comic: (id, personId, designId) =>
    fetch(`${API}/api/spaces/${id}/comic`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ person_id: personId, design_id: designId }),
    }).then(handle),
  talk: (id, personId, message, history, designId) =>
    fetch(`${API}/api/spaces/${id}/talk`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ person_id: personId, message, history, design_id: designId ?? null }),
    }).then(handle),
  renderRoom: (id, designId, roomId) =>
    fetch(`${API}/api/spaces/${id}/designs/${designId}/render`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ room_id: roomId }),
    }).then(handle),
  family: (id) => fetch(`${API}/api/spaces/${id}/family`).then(handle),
  describeFamily: (id, text) =>
    fetch(`${API}/api/spaces/${id}/family`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }).then(handle),
  resetFamily: (id) => fetch(`${API}/api/spaces/${id}/family`, { method: 'DELETE' }).then(handle),
  improve: (id, body) =>
    fetch(`${API}/api/spaces/${id}/improve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(handle),
  improveProgress: (id, job, since) => fetch(`${API}/api/spaces/${id}/improve/${job}?since=${since}`).then(handle),
  designs: (id) => fetch(`${API}/api/spaces/${id}/designs`).then(handle),
  catalog: (pack) => fetch(`${API}/api/catalog/${pack}`).then(handle),
  saveSpace: (id, { grid, rooms, entrance, items, doors }) =>
    fetch(`${API}/api/spaces/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ grid, rooms, entrance, items, doors }),
    }).then(handle),
  imageUrl: (id) => `/api/spaces/${id}/image`,
}
