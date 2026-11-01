// Cloudflare Pages Function: every /api/... request goes to the backend on Railway.
// The browser only ever talks to the Pages address, so there is no CORS to set up and
// picture links like /api/spaces/<id>/image keep working as they are.
// Set BACKEND_URL in Pages → Settings → Variables (for example https://lifespace-production.up.railway.app).
export async function onRequest({ request, env }) {
  const backend = (env.BACKEND_URL || '').replace(/\/$/, '')
  if (!backend) return new Response('BACKEND_URL is not set on this Pages project', { status: 500 })
  const url = new URL(request.url)
  const target = backend + url.pathname + url.search
  const headers = new Headers(request.headers)
  headers.set('x-forwarded-for', request.headers.get('cf-connecting-ip') || '')
  headers.delete('host')
  return fetch(target, {
    method: request.method,
    headers,
    body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
    redirect: 'manual',
  })
}
