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
  redesign: (id, budget, goals) =>
    fetch(`/api/spaces/${id}/designs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ budget, goals }),
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
