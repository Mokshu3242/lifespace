export const CODES = { WALL: -1, OUTSIDE: -2, FIXTURE: -4 }

// Soft colors that stay readable under black labels; picked by room id
const PALETTE = [
  '#8fb9a8', '#f2c57c', '#a3b8e0', '#e8a39b', '#c6b3e0', '#9fd3c7',
  '#f0d39a', '#b7cf8f', '#e3b7c8', '#a9c6d9', '#d9c3a0', '#b0d0b0',
]

export const roomColor = (id) => PALETTE[id % PALETTE.length]

export const KIND_LABEL = {
  room: 'Room', open: 'Open area', bath: 'Bathroom', closet: 'Closet', outdoor: 'Outdoor',
}

export function areaSqft(grid, id, cellIn) {
  let n = 0
  for (const row of grid) for (const v of row) if (v === id) n++
  return Math.round(n * (cellIn / 12) ** 2 * 10) / 10
}

// Which model did a step, in words a judge understands
const MODEL_LABEL = {
  meta: 'Meta Muse Spark 1.3',
  baseten: 'Meta Muse Spark Open',
  'meta-image': 'Meta Muse Image',
  cloudflare: 'Llama 4 Scout (Cloudflare)',
  ollama: 'Qwen 2.5 VL (local)',
  groq: 'Qwen (Groq)',
  gemini: 'Gemini (local test)',
  mock: 'mock model',
}

export function modelLabel(provider) {
  if (!provider) return 'unknown model'
  const base = provider.replace(' (cache)', '')
  return (MODEL_LABEL[base] || base) + (provider.endsWith('(cache)') ? ' · saved answer' : '')
}

export function isMeta(provider) {
  return Boolean(provider) && (provider.startsWith('meta') || provider.startsWith('baseten'))
}