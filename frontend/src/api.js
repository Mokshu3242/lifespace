async function handle(r) {
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || `Request failed (${r.status})`)
  return data
}

export const api = {
  health: () => fetch('/api/health').then(handle),
  uploadPlan: (file) => {
    const body = new FormData()
    body.append('file', file)
    return fetch('/api/spaces', { method: 'POST', body }).then(handle)
  },
  getSpace: (id) => fetch(`/api/spaces/${id}`).then(handle),
  saveSpace: (id, { grid, rooms, entrance }) =>
    fetch(`/api/spaces/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ grid, rooms, entrance }),
    }).then(handle),
  imageUrl: (id) => `/api/spaces/${id}/image`,
}
