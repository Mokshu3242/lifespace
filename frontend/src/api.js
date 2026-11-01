async function handle(r) {
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || `Request failed (${r.status})`)
  return data
}

export const api = {
  health: () => fetch('/api/health').then(handle),
  uploadPlan: (file, { fresh = false, pack = 'home', describe = '' } = {}) => {
    const body = new FormData()
    body.append('file', file)
    const q = new URLSearchParams({ pack, describe: describe.trim() })
    if (fresh) q.set('fresh', 'true')
    return fetch(`/api/spaces?${q}`, { method: 'POST', body }).then(handle)
  },
  getSpace: (id) => fetch(`/api/spaces/${id}`).then(handle),
  listSpaces: () => fetch('/api/spaces').then(handle),
  future: (id, years, designId) =>
    fetch(`/api/spaces/${id}/future`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ years, design_id: designId ?? null }),
    }).then(handle),
  compare: (ids, family) =>
    fetch('/api/spaces/compare', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids, family }),
    }).then(handle),
  uploadStreet: (file) => {
    const body = new FormData()
    body.append('file', file)
    return fetch('/api/streets', { method: 'POST', body }).then(handle)
  },
  getStreet: (id) => fetch(`/api/streets/${id}`).then(handle),
  redesignStreet: (id, budget, goals) =>
    fetch(`/api/streets/${id}/designs`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ budget, goals }),
    }).then(handle),
  drawStreet: (id, n) => fetch(`/api/streets/${id}/designs/${n}/render`, { method: 'POST' }).then(handle),
  redesign: (id, budget, goals, style = 'small') =>
    fetch(`/api/spaces/${id}/designs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ budget, goals, style }),
    }).then(handle),
  simulate: (id, designId) =>
    fetch(`/api/spaces/${id}/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ design_id: designId }),
    }).then(handle),
  renderRoom: (id, designId, roomId) =>
    fetch(`/api/spaces/${id}/designs/${designId}/render`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ room_id: roomId }),
    }).then(handle),
  family: (id) => fetch(`/api/spaces/${id}/family`).then(handle),
  describeFamily: (id, text) =>
    fetch(`/api/spaces/${id}/family`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }).then(handle),
  resetFamily: (id) => fetch(`/api/spaces/${id}/family`, { method: 'DELETE' }).then(handle),
  improve: (id, body) =>
    fetch(`/api/spaces/${id}/improve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(handle),
  improveProgress: (id, job, since) => fetch(`/api/spaces/${id}/improve/${job}?since=${since}`).then(handle),
  designs: (id) => fetch(`/api/spaces/${id}/designs`).then(handle),
  catalog: (pack) => fetch(`/api/catalog/${pack}`).then(handle),
  saveSpace: (id, { grid, rooms, entrance, items }) =>
    fetch(`/api/spaces/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ grid, rooms, entrance, items }),
    }).then(handle),
  imageUrl: (id) => `/api/spaces/${id}/image`,
}
